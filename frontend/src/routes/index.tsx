import React, { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import LoginPage from '../pages/LoginPage';
import RegisterPage from '../pages/RegisterPage';
import ChatPage from '../pages/ChatPage';
// Diğer sayfalar gerekiyorsa buraya import edilir
// import ChatPage from '../pages/ChatPage';

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [loading, setLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const location = useLocation();

  useEffect(() => {
    fetch('/api/auth/whoami/')
      .then(res => res.ok ? setIsAuthenticated(true) : setIsAuthenticated(false))
      .catch(() => setIsAuthenticated(false))
      .finally(() => setLoading(false));
  }, [location.pathname]);

  if (loading) return null; // veya bir loading spinner
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
};

const AppRoutes = () => (
  <BrowserRouter>
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/" element={
        <ProtectedRoute>
          <ChatPage />
        </ProtectedRoute>
      } />
      <Route path="*" element={<Navigate to="/" />} />
      {/* <Route path="/" element={<ChatPage />} /> */}
      {/* Diğer route'lar buraya eklenebilir */}
    </Routes>
  </BrowserRouter>
);

export default AppRoutes; 