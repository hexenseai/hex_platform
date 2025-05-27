import React, { useState } from 'react';
import { Box, TextField, Button, Card, Typography, Alert, CircularProgress } from '@mui/material';
import { AccountCircle, Lock, Email } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

interface RegisterFormValues {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
}

const RegisterPage: React.FC = () => {
  const API_HOST = import.meta.env.VITE_APP_API_HOST;
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState<RegisterFormValues>({
    first_name: '',
    last_name: '',
    email: '',
    password: '',
  });

  const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`${API_HOST}/api/auth/register/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(form),
      });
      if (response.ok) {
        // Kayıt başarılı, otomatik login
        const loginResponse = await fetch(`${API_HOST}/api/auth/login/`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ username: form.email, password: form.password }),
        });
        if (loginResponse.ok) {
          navigate('/');
        } else {
          setError('Kayıt başarılı ancak otomatik giriş yapılamadı. Lütfen giriş yapın.');
        }
      } else {
        const errorData = await response.json();
        setError(errorData.error || errorData.detail || 'Kayıt başarısız.');
      }
    } catch (err) {
      setError('Bir ağ hatası oluştu veya sunucuya ulaşılamadı.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', width: '100vw', bgcolor: '#f0f2f5' }}>
      <Card sx={{ width: 400, boxShadow: 3, p: 4 }}>
        <Box sx={{ textAlign: 'center', mb: 4 }}>
          <Typography variant="h4" color="primary" fontWeight={700} gutterBottom>Kayıt Ol</Typography>
        </Box>
        {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}
        <form onSubmit={onSubmit} autoComplete="off">
          <TextField
            name="first_name"
            label="Ad"
            value={form.first_name}
            onChange={onChange}
            fullWidth
            margin="normal"
            required
            InputProps={{ startAdornment: <AccountCircle sx={{ mr: 1 }} /> }}
          />
          <TextField
            name="last_name"
            label="Soyad"
            value={form.last_name}
            onChange={onChange}
            fullWidth
            margin="normal"
            required
            InputProps={{ startAdornment: <AccountCircle sx={{ mr: 1 }} /> }}
          />
          <TextField
            name="email"
            label="E-posta"
            type="email"
            value={form.email}
            onChange={onChange}
            fullWidth
            margin="normal"
            required
            InputProps={{ startAdornment: <Email sx={{ mr: 1 }} /> }}
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
            Kayıt Ol
          </Button>
          <Button
            variant="text"
            fullWidth
            sx={{ p: 0, mt: 1 }}
            onClick={() => navigate('/login')}
          >
            Giriş Yap
          </Button>
        </form>
      </Card>
    </Box>
  );
};

export default RegisterPage; 