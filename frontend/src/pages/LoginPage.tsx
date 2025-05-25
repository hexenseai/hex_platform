// src/pages/LoginPage.tsx
import React, { useState, useEffect } from 'react';
import { Form, Input, Button, Card, Typography, Alert } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { ApiError } from '../types'; // Tiplerimizi import edelim
import api from '../services/api';

const { Title } = Typography;

// Ant Design Form'un onFinish fonksiyonundan gelen values tipi
interface LoginFormValues {
  username?: string;
  password?: string;
  remember?: boolean;
}


const LoginPage: React.FC = () => {
  const API_HOST = import.meta.env.VITE_APP_API_HOST;
  const navigate = useNavigate();
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');

  const onFinish = async (values: LoginFormValues) => {
    setLoading(true);
    setError('');
    try {
      const response = await api.post(`token/`, {
        username: values.username,
        password: values.password,
      });
      localStorage.setItem('access_token', response.data.access);
      localStorage.setItem('refresh_token', response.data.refresh);
      console.log('Login successful, navigating to /');
      navigate('/');
    } catch (error: any) {
      console.error('Login failed:', error);
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
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', width: '100vw', background: '#f0f2f5' }}>
      <Card style={{ width: 400, boxShadow: '0 4px 12px rgba(0,0,0,0.15)' }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          {/* <img src="/path/to/your/logo.png" alt="Hexense Logo" style={{ height: 60, marginBottom: 16 }} /> */}
          <Title level={2} style={{ color: '#1890ff' }}>Hexense AI Platform</Title>
        </div>
        {error && <Alert message={error} type="error" showIcon closable style={{ marginBottom: 24 }} />}
        <Form
          name="login_form"
          initialValues={{ remember: true }}
          onFinish={onFinish}
          size="large"
        >
          <Form.Item
            name="username"
            rules={[{ required: true, message: 'Lütfen kullanıcı adınızı girin!' }]}
          >
            <Input prefix={<UserOutlined />} placeholder="Kullanıcı Adı" />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[{ required: true, message: 'Lütfen şifrenizi girin!' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="Şifre" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} style={{ width: '100%' }}>
              Giriş Yap
            </Button>
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="link" style={{ padding: 0 }} onClick={() => navigate('/register')}>
              Kayıt Ol
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

export default LoginPage;