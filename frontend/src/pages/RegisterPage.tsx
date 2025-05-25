import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, Alert } from 'antd';
import { UserOutlined, LockOutlined, MailOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

const { Title } = Typography;

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

  const onFinish = async (values: RegisterFormValues) => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`${API_HOST}/api/auth/register/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(values),
      });
      if (response.ok) {
        // Kayıt başarılı, otomatik login
        const loginResponse = await fetch(`${API_HOST}/api/auth/login/`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ username: values.email, password: values.password }),
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
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', width: '100vw', background: '#f0f2f5' }}>
      <Card style={{ width: 400, boxShadow: '0 4px 12px rgba(0,0,0,0.15)' }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <Title level={2} style={{ color: '#1890ff' }}>Kayıt Ol</Title>
        </div>
        {error && <Alert message={error} type="error" showIcon closable style={{ marginBottom: 24 }} />}
        <Form name="register_form" onFinish={onFinish} size="large">
          <Form.Item name="first_name" rules={[{ required: true, message: 'Lütfen adınızı girin!' }]}> 
            <Input prefix={<UserOutlined />} placeholder="Ad" />
          </Form.Item>
          <Form.Item name="last_name" rules={[{ required: true, message: 'Lütfen soyadınızı girin!' }]}> 
            <Input prefix={<UserOutlined />} placeholder="Soyad" />
          </Form.Item>
          <Form.Item name="email" rules={[{ required: true, type: 'email', message: 'Geçerli bir e-posta girin!' }]}> 
            <Input prefix={<MailOutlined />} placeholder="E-posta" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: 'Lütfen şifre belirleyin!' }]}> 
            <Input.Password prefix={<LockOutlined />} placeholder="Şifre" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} style={{ width: '100%' }}>
              Kayıt Ol
            </Button>
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="link" style={{ padding: 0 }} onClick={() => navigate('/login')}>
              Giriş Yap
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

export default RegisterPage; 