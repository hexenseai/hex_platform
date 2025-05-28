// src/pages/LoginPage.tsx
import React, { useState, useEffect } from 'react';
import { Box, TextField, Button, Card, Typography, Alert, CircularProgress } from '@mui/material';
import { AccountCircle, Lock } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import type { ApiError } from '../types'; // Tiplerimizi import edelim
import api from '../services/api';
import logoFull from '../assets/logo/logo_full.png';

const LoginPage: React.FC = () => {
  const API_HOST = import.meta.env.VITE_APP_API_HOST;
  const navigate = useNavigate();
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [form, setForm] = useState({ username: '', password: '' });

  const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const response = await api.post(`token/`, {
        username: form.username,
        password: form.password,
      });
      localStorage.setItem('access_token', response.data.access);
      localStorage.setItem('refresh_token', response.data.refresh);
      navigate('/');
    } catch (error: any) {
      if (error.response && error.response.data) {
        setError(error.response.data.detail || 'Giriş başarısız. Lütfen bilgilerinizi kontrol edin.');
      } else {
        setError('Bir ağ hatası oluştu veya sunucuya ulaşılamadı.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    window.location.href = 'http://localhost:8000/accounts/google/login/';
  };

  useEffect(() => {
    if (window.location.pathname === '/accounts/profile/') {
      fetch('http://localhost:8000/accounts/profile/', {
        credentials: 'include',
      })
        .then(res => res.json())
        .then(data => {
          if (data.access && data.refresh) {
            localStorage.setItem('access', data.access);
            localStorage.setItem('refresh', data.refresh);
          }
        });
    }
  }, []);

  return (
    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', width: '100vw', bgcolor: theme => theme.palette.background.customBackground }}>
      <Card sx={{ width: 400, boxShadow: 3, p: 4, bgcolor: theme => theme.palette.background.paper, borderRadius: 4 }}>
        <Box sx={{ textAlign: 'center', mb: 4 }}>
          <img src={logoFull} alt="Hexense Logo" style={{ height: 48, marginBottom: 16 }} />
        </Box>
        {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}
        <form onSubmit={onSubmit} autoComplete="off">
          <TextField
            name="username"
            label="Kullanıcı Adı"
            value={form.username}
            onChange={onChange}
            fullWidth
            margin="normal"
            required
            InputProps={{ startAdornment: <AccountCircle sx={{ mr: 1 }} /> }}
          />
          <TextField
            name="password"
            label="Şifre"
            type="password"
            value={form.password}
            onChange={onChange}
            fullWidth
            margin="normal"
            required
            InputProps={{ startAdornment: <Lock sx={{ mr: 1 }} /> }}
          />
          <Button
            type="submit"
            variant="contained"
            color="primary"
            fullWidth
            sx={{ mt: 2, mb: 1 }}
            disabled={loading}
            startIcon={loading ? <CircularProgress size={20} color="inherit" /> : null}
          >
            Giriş Yap
          </Button>
          <Button
            variant="text"
            fullWidth
            sx={{ p: 0, mt: 1 }}
            onClick={() => navigate('/register')}
          >
            Kayıt Ol
          </Button>
        </form>
      </Card>
    </Box>
  );
};

export default LoginPage;