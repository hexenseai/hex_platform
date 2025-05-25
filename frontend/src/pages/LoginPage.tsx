// src/pages/LoginPage.tsx
import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, Alert } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { ApiError } from '../types'; // Tiplerimizi import edelim

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
      const response = await fetch(`${API_HOST}/api/auth/login/`, { // Django API endpoint'iniz
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          // CSRF token Django session auth'da form gönderiminde gerekebilir,
          // API için genellikle session cookie yeterlidir.
          // Django'nun CSRF ayarlarını ve API'nizin nasıl korunduğunu kontrol edin.
        },
        body: JSON.stringify({ username: values.username, password: values.password }),
      });

      if (response.ok) {
        // const data: LoginResponse = await response.json(); // Yanıtı parse et
        // TODO: Auth state'ini güncelle (Context API veya Zustand/Redux ile)
        // Örneğin, localStorage'a token kaydetme veya bir auth context'i güncelleme
        // localStorage.setItem('isAuthenticated', 'true'); // Çok basit bir örnek
        console.log("Login successful, navigating to /"); // Log eklendi
        navigate('/');
        // window.location.href = '/'; // Sayfa yenilemesiyle yönlendirme (state kaybına yol açar, navigate daha iyi)
      } else {
        const errorData: ApiError = await response.json();
        setError(errorData.error || errorData.detail || 'Giriş başarısız. Lütfen bilgilerinizi kontrol edin.');
      }
    } catch (err) {
      console.error("Login request failed:", err); // Log eklendi
      setError('Bir ağ hatası oluştu veya sunucuya ulaşılamadı.');
    } finally {
      setLoading(false);
    }
  };

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