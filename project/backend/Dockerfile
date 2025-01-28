FROM golang:1.23.5

# Imposta la directory di lavoro
WORKDIR /app

# Copia i file Go
COPY go.mod go.sum ./
RUN go mod tidy
RUN go mod download

# Copia il codice
COPY . .

# Compila il backend
RUN go build -o main .

# Esponi la porta 8080
EXPOSE 8080

# Comando per avviare l'app
CMD ["./main"]
