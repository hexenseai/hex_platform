// src/main.tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App'; // Ana App bileşeniniz
import 'antd/dist/reset.css'; // Ant Design stilleri
import './index.css'; // Kendi genel stilleriniz (Tailwind için de)

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);