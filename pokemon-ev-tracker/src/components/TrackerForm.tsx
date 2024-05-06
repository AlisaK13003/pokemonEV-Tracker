import React, { useState } from 'react';
import { PokemonEV } from '../types';

const TrackerForm: React.FC = () => {
  const [evs, setEvs] = useState<PokemonEV>({ name: '', hp: 0, attack: 0, defense: 0, specialAttack: 0, specialDefense: 0, speed: 0 });

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    setEvs(prevEvs => ({
      ...prevEvs,
      [name]: value
    }));
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    console.log(evs); // Process or send this data to a backend or state management
  };

  return (
    <form onSubmit={handleSubmit}>
      <input type="text" name="name" value={evs.name} onChange={handleChange} placeholder="Pokemon Name" />
      {/* Repeat for other fields */}
      <button type="submit">Track EV</button>
    </form>
  );
};

export default TrackerForm;
