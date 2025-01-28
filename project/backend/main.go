package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
	influxdb2 "github.com/influxdata/influxdb-client-go/v2"
)

// InfluxDB configuration from environment variables
var (
	influxURL    = os.Getenv("INFLUXDB_URL")
	influxToken  = os.Getenv("INFLUXDB_TOKEN")
	influxOrg    = os.Getenv("INFLUXDB_ORG")
	influxBucket = os.Getenv("INFLUXDB_BUCKET")
	sensorsAPI   = os.Getenv("SENSORS_API")
)

var consumerInfo = make(map[string]map[string]map[string]string)

func main() {
	// Check if environment variables are set
	if influxURL == "" || influxToken == "" || influxOrg == "" || influxBucket == "" {
		log.Fatal("InfluxDB environment variables are not set correctly")
	}

	// Initialize InfluxDB client
	client := influxdb2.NewClient(influxURL, influxToken)
	defer client.Close()

	// Create a Gin instance
	router := gin.Default()

	// Configure CORS middleware
	router.Use(cors.Default())

	// Endpoint to check server health
	router.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "healthy"})
	})

	// Endpoint to return members and consumers retrieved from InfluxDB
	router.GET("/members", func(c *gin.Context) {
		queryAPI := client.QueryAPI(influxOrg)
		query := `import "influxdata/influxdb/schema"
				schema.tagValues(
				bucket: "` + influxBucket + `",
				tag: "member_id"
				)`
		result, err := queryAPI.Query(c, query)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}

		members := make(map[string][]string)
		for result.Next() {
			memberID := result.Record().ValueByKey("_value").(string)
			members[memberID] = []string{}
			consumerInfo[memberID] = make(map[string]map[string]string)
		}

		for memberID := range members {
			query = `import "influxdata/influxdb/schema"
					schema.tagValues(
					bucket: "` + influxBucket + `",
					tag: "topic"
					) |> filter(fn: (r) => r._value =~ /consumer\/taudelta\/` + memberID + `/)`
			result, err = queryAPI.Query(c, query)
			if err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				return
			}

			for result.Next() {
				topic := result.Record().ValueByKey("_value").(string)
				consumerID := strings.Split(topic, "/")[len(strings.Split(topic,"/")) - 1]
				
				// Query to get the "cons" tag for each consumer
				queryCons := `from(bucket: "` + influxBucket + `")
					|> range(start: -30s)
					|> filter(fn: (r) => r["_measurement"] == "tau_delta" and r["consumer_id"] == "` + consumerID + `" and r["member_id"] == "` + memberID + `")
					|> last()`
				resultCons, err := queryAPI.Query(c, queryCons)
				if err != nil {
					c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
					return
				}

				var cons string
				if resultCons.Next() {
					cons = resultCons.Record().ValueByKey("cons").(string)
				}

				consumerInfo[memberID][consumerID] = map[string]string{
					"topic": topic,
					"cons":  cons,
				}
				members[memberID] = append(members[memberID], consumerID)
			}
		}

		c.JSON(http.StatusOK, members)
	})

	// Endpoint to insert data into InfluxDB
	router.POST("/insert_tau_delta", func(c *gin.Context) {
		// Get parameters from JSON request
		var request struct {
			ConsumerID string  `json:"consumer_id" binding:"required"`
			MemberID   string  `json:"member_id" binding:"required"`
			Tau        float64 `json:"tau" binding:"required"`
			Delta      float64 `json:"delta" binding:"required"`
		}

		if err := c.ShouldBindJSON(&request); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request data"})
			return
		}

		// Get the current timestamp in nanoseconds
		timestamp := time.Now()

		// Write data to InfluxDB
		writeAPI := client.WriteAPIBlocking(influxOrg, influxBucket)
		point := influxdb2.NewPointWithMeasurement("tau_delta").
			AddTag("consumer_id", request.ConsumerID).
			AddTag("member_id", request.MemberID).
			AddTag("cons", consumerInfo[request.MemberID][request.ConsumerID]["cons"]).
			AddTag("topic", consumerInfo[request.MemberID][request.ConsumerID]["topic"]).
			AddField("active", false).
			AddField("tau", request.Tau).
			AddField("delta", request.Delta).
			SetTime(timestamp)
		
		log.Println(point)

		// Write the point to the database
		if err := writeAPI.WritePoint(c, point); err != nil {
			log.Printf("Error writing to InfluxDB: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to insert data"})
			return
		}

		// Call the sensors API to update tau and delta
		go func() {
			url := sensorsAPI + "/update_tau_delta"
			data := map[string]interface{}{
				"member_id":   request.MemberID,
				"consumer_id": request.ConsumerID,
				"tau":         request.Tau,
				"delta":       request.Delta,
			}
			jsonData, err := json.Marshal(data)
			if err != nil {
				log.Printf("Error marshaling data: %v", err)
				return
			}
			resp, err := http.Post(url, "application/json", strings.NewReader(string(jsonData)))
			if err != nil {
				log.Printf("Error calling sensors API: %v", err)
			} else {
				defer resp.Body.Close()
				if resp.StatusCode != http.StatusOK {
					log.Printf("Sensors API returned status code %d", resp.StatusCode)
				}
			}
		}()

		// Respond with a confirmation JSON
		c.JSON(http.StatusOK, gin.H{
			"message":     "Data inserted successfully",
			"consumer_id": request.ConsumerID,
			"member_id":   request.MemberID,
			"tau":         request.Tau,
			"delta":       request.Delta,
		})

		
	})

	// Start the server on port 8080
	log.Println("Server running on port 8080")
	router.Run(":8080")
}
