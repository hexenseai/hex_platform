// src/App.tsx
import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import LoginPage from './pages/LoginPage.tsx';
import ChatPage from './pages/ChatPage.tsx';
// import PrivateRoute from './routes/PrivateRoute'; // AuthContext ile kullanılacak
// import { AuthProvider, useAuth } from './context/AuthContext'; // AuthContext için

// function AppContent() {
//   const { isAuthenticated } = useAuth(); // AuthContext'ten alınacak
//   return (
//     <Routes>
//       <Route path="/login" element={!isAuthenticated ? <LoginPage /> : <Navigate to="/" />} />
//       <Route
//         path="/*" // Diğer tüm yollar için
//         element={
//           <PrivateRoute>
//             <ChatPage /> 
//           </PrivateRoute>
//         }
//       />
//       {/* <Route path="*" element={<Navigate to={isAuthenticated ? "/" : "/login"} />} /> */}
//     </Routes>
//   );
// }

function App() {
  // Şimdilik AuthProvider ve PrivateRoute olmadan basit yapı:
  return (
    <Router>
      {/* <AuthProvider> */}
        {/* <AppContent /> */}
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<ChatPage />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      {/* </AuthProvider> */}
    </Router>
  );
}

export default App;