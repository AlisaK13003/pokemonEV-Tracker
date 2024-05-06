import React from 'react';
import '../styles/index.css'; // Update this path if the structure shown is incorrect
import TrackerForm from './TrackerForm'; // Corrected import path, assuming TrackerForm.tsx is in the same directory

const App: React.FC = () => {
  return (
    <div className="App">
      <header className="App-header">
        <h1>Pokémon EV Tracker</h1>
        <TrackerForm />
      </header>
    </div>
  );
}

export default App;
