import React, { useState, useEffect } from 'react';
import './App.css';

const REACT_APP_BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8080';

function App() {
  const [members, setMembers] = useState({});
  const [selectedMember, setSelectedMember] = useState('');
  const [selectedConsumer, setSelectedConsumer] = useState('');
  const [tau, setTau] = useState('');
  const [delta, setDelta] = useState('');

  useEffect(() => {
    fetch(`${REACT_APP_BACKEND_URL}/members`)
      .then(response => response.json())
      .then(data => {
        setMembers(data);
        console.log('Members fetched:', data);
      })
      .catch(error => console.error('Error fetching members:', error));
  }, []);

  const handleSubmit = (event) => {
    event.preventDefault();
    const request = {
      consumer_id: selectedConsumer,
      member_id: selectedMember,
      tau: parseFloat(tau),
      delta: parseFloat(delta)
    };

    fetch(`${REACT_APP_BACKEND_URL}/insert_tau_delta`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(request)
    })
      .then(response => response.json())
      .then(data => console.log('Success:', data))
      .catch(error => console.error('Error:', error));
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Insert Tau and Delta</h1>
      </header>
      <form onSubmit={handleSubmit} className="tau-delta-form">
        <div className="form-group">
          <label htmlFor="member-select" className="form-label">Member:</label>
          <select id="member-select" className="form-control" value={selectedMember} onChange={e => setSelectedMember(e.target.value)}>
            <option value="">Select a member</option>
            {Object.keys(members).map(member => (
              <option key={member} value={member}>{member}</option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label htmlFor="consumer-select" className="form-label">Consumer:</label>
          <select id="consumer-select" className="form-control" value={selectedConsumer} onChange={e => setSelectedConsumer(e.target.value)} disabled={!selectedMember}>
            <option value="">Select a consumer</option>
            {selectedMember && members[selectedMember].map(consumer => (
              <option key={consumer} value={consumer}>{consumer}</option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label htmlFor="tau-input" className="form-label">Tau:</label>
          <input id="tau-input" type="number" className="form-control" value={tau} onChange={e => setTau(e.target.value)} required />
        </div>
        <div className="form-group">
          <label htmlFor="delta-input" className="form-label">Delta:</label>
          <input id="delta-input" type="number" className="form-control" value={delta} onChange={e => setDelta(e.target.value)} required min={parseFloat(tau) + 60} />
        </div>
        <button type="submit" className="btn btn-primary">Submit</button>
      </form>
    </div>
  );
}

export default App;
