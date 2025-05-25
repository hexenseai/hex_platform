// frontend/src/pages/ChatPage.tsx

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Layout, Menu, Select, Avatar, Dropdown, Space, Button, Typography, Spin, Input, Alert, App as AntApp, message, notification } from 'antd';
import type { MenuProps } from 'antd';
import { marked } from 'marked';

import {
  UserOutlined,
  MessageOutlined,
  ExperimentOutlined,
  SettingOutlined,
  DownOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  EditOutlined,
  LogoutOutlined,
  PlusOutlined,
  SendOutlined, // Gönderme ikonu için
  LoadingOutlined // Yükleme ikonu için
} from '@ant-design/icons';

import type {
  UserInfo,
  GptPackageOption,
  UserProfileData,
  WhoAmIResponse,
  UserProfileOption,
  ChatMessage
} from '../types';

const { Header, Sider, Content } = Layout;
const { Text, Paragraph } = Typography;

// Marked ayarları
marked.setOptions({
  breaks: true,
  gfm: true,
  // headerIds: false,
  //mangle: false,
  // sanitize: true, // DOMPurify gibi bir kütüphane ile yapmak daha iyi olabilir
});


const ChatPage: React.FC = () => {
  const API_HOST = import.meta.env.VITE_APP_API_HOST;
  const API_WS_HOST = import.meta.env.VITE_APP_API_WS_HOST;
  const [collapsed, setCollapsed] = useState<boolean>(false);
  const [userProfiles, setUserProfiles] = useState<UserProfileOption[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);
  const [gptPackages, setGptPackages] = useState<GptPackageOption[]>([]);
  const [selectedGptPackage, setSelectedGptPackage] = useState<GptPackageOption | null>(null);
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [loadingWhoAmI, setLoadingWhoAmI] = useState<boolean>(true);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [currentMessageInput, setCurrentMessageInput] = useState<string>('');
  const [isSendingMessage, setIsSendingMessage] = useState<boolean>(false);
  const [webSocket, setWebSocket] = useState<WebSocket | null>(null);
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [showTypingIndicator, setShowTypingIndicator] = useState<boolean>(false);

  const chatBoxRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    if (chatBoxRef.current) {
      chatBoxRef.current.scrollTop = chatBoxRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // --- WebSocket Yönetimi ---
  const connectWebSocket = useCallback(() => {
    const accessToken = localStorage.getItem('access_token');
    if (!accessToken) {
        message.error("Access token bulunamadı. Lütfen tekrar giriş yapın.");
        return;
    }
    const wsUrl = `${API_WS_HOST}/ws/chat/?token=${accessToken}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log("WebSocket connection opened.");
      setWsConnected(true);
      setWebSocket(ws);
      if (selectedProfileId) {
        console.log("WS Open: Sending initial profile_change:", selectedProfileId);
        ws.send(JSON.stringify({ type: 'profile_change', profile_id: selectedProfileId }));
      }
      if (selectedGptPackage) {
        console.log("WS Open: Sending initial gpt_package_change:", selectedGptPackage.id);
        ws.send(JSON.stringify({ type: 'gpt_package_change', gpt_package_id: selectedGptPackage.id }));
      }
    };

    ws.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data as string);
        console.log("WebSocket RCV:", data);
      } catch (e) {
        console.error("Invalid JSON from WS:", event.data);
        return;
      }

      switch (data.type) {
        case 'connection_established':
          message.success(data.message || "Bağlantı kuruldu!");
          break;
        case 'profile_change_ack':
          console.log("Profile change acknowledged by server:", data.profile_id);
          // Profil backend'de set edildi. Bu profile ait GPT paketlerini yükle/göster.
          const ackProfile = userProfiles.find(p => p.value === data.profile_id);
          if (ackProfile) {
            setGptPackages(ackProfile.gptPackages || []);
            const defaultPkg = ackProfile.gptPackages?.find(pkg => pkg.is_default) || ackProfile.gptPackages?.[0];
            if (defaultPkg && webSocket) { // webSocket'in null olmadığını kontrol et
                console.log("ProfileAck: Sending gpt_package_change for default:", defaultPkg.id);
                webSocket.send(JSON.stringify({ type: 'gpt_package_change', gpt_package_id: defaultPkg.id }));
                setSelectedGptPackage(defaultPkg); // Client state'ini de güncelle
            } else if (ackProfile.gptPackages && ackProfile.gptPackages.length > 0 && webSocket) {
                console.log("ProfileAck: Sending gpt_package_change for first available:", ackProfile.gptPackages[0].id);
                webSocket.send(JSON.stringify({ type: 'gpt_package_change', gpt_package_id: ackProfile.gptPackages[0].id }));
                setSelectedGptPackage(ackProfile.gptPackages[0]); // Client state'ini de güncelle
            } else {
                setSelectedGptPackage(null); // Paket yoksa null yap
            }
          }
          break;
        case 'gpt_package_change_ack':
          console.log("GPT package change acknowledged:", data.gpt_package_id, "Conv ID:", data.conversation_id);
          setCurrentConversationId(data.conversation_id);
          // Paket değiştiğinde mesajları temizle (yeni bir bağlam)
          setMessages([]);
          break;
        case 'new_conversation_ack':
          console.log("New conversation acknowledged:", data.conversation_id);
          setCurrentConversationId(data.conversation_id);
          setMessages([]); // Yeni sohbet için mesajları temizle
          break;
        case 'assistant_message_chunk':
          setShowTypingIndicator(false); // Chunk gelmeye başladı, typing indicator'ı kaldır
          setMessages(prevMessages => {
            const lastMessage = prevMessages[prevMessages.length - 1];
            if (lastMessage && lastMessage.sender === 'assistant' && lastMessage.isStreaming) {
              // Mevcut stream edilen mesaja ekle
              return [
                ...prevMessages.slice(0, -1),
                { ...lastMessage, content: lastMessage.content + data.chunk }
              ];
            } else {
              // Yeni bir asistan mesajı başlat
              return [
                ...prevMessages,
                {
                  id: `asst-${Date.now()}`, // Basit bir ID
                  sender: 'assistant',
                  content: data.chunk,
                  timestamp: new Date(),
                  gptPackageName: selectedGptPackage?.label,
                  isStreaming: true,
                }
              ];
            }
          });
          break;
        case 'assistant_stream_finalized':
           console.log("Assistant stream finalized.");
           setShowTypingIndicator(false);
           console.log("isSendingMessage before set to false:", isSendingMessage);
           setIsSendingMessage(false);
           setTimeout(() => { console.log("isSendingMessage after set to false:", isSendingMessage); }, 100);
           setMessages(prevMessages => {
            const lastMessage = prevMessages[prevMessages.length - 1];
            if (lastMessage && lastMessage.sender === 'assistant' && lastMessage.isStreaming) {
              // Stream bitti, Markdown'ı parse et ve isStreaming'i false yap
              return [
                ...prevMessages.slice(0, -1),
                { ...lastMessage, isStreaming: false, content: marked.parse(lastMessage.content) as string }
              ];
            }
            return prevMessages;
          });
           break;
        case 'ui_actions':
          console.log("UI Actions received:", data.actions);
          // TODO: Gelen UI aksiyonlarını işle (örn: modal, grafik)
          // handleUIActions(data.actions);
          notification.info({
            message: 'UI Aksiyonu Alındı',
            description: JSON.stringify(data.actions, null, 2),
          });
          break;
        case 'error':
          console.error("WebSocket Error:", data.message);
          setShowTypingIndicator(false);
          setMessages(prev => [...prev, {
            id: `err-${Date.now()}`, sender: 'system_error', content: `Hata: ${data.message}`, timestamp: new Date()
          }]);
          message.error(`Sunucu Hatası: ${data.message}`);
          break;
        default:
          console.warn("Unknown WebSocket message type:", data.type);
      }
    };

    ws.onclose = (event) => {
      console.warn("WebSocket connection closed:", event.reason, "Code:", event.code);
      setWsConnected(false);
      setWebSocket(null);
      // Belirli kapanma kodları için yeniden bağlanmayı deneyebiliriz
      if (event.code !== 1000) { // 1000 normal kapanma
        message.error("Bağlantı kesildi. 5 saniye içinde yeniden deneniyor...");
        setTimeout(connectWebSocket, 5000);
      }
    };

    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
      // message.error("WebSocket bağlantı hatası oluştu.");
      // onclose zaten tetiklenecektir.
    };

    // setWebSocket(ws); // ws.onopen içinde set ediliyor

    return () => { // Cleanup fonksiyonu
      if (ws && ws.readyState === WebSocket.OPEN) {
        console.log("Closing WebSocket connection on component unmount.");
        ws.close(1000, "Component unmounting");
      }
      setWebSocket(null);
      setWsConnected(false);
    };
  }, [API_WS_HOST, message, notification]);

  useEffect(() => {
    const cleanupWs = connectWebSocket();
    return cleanupWs; // Component unmount olduğunda WebSocket'i kapat
  }, [connectWebSocket]); // Sadece component mount/unmount olduğunda çalışsın diye.

  // Profil değiştiğinde WebSocket'e bildir
  useEffect(() => {
    if (webSocket && wsConnected && selectedProfileId) {
      webSocket.send(JSON.stringify({ type: 'profile_change', profile_id: selectedProfileId }));
    }
  }, [selectedProfileId, webSocket, wsConnected]);

  // GPT package değiştiğinde WebSocket'e bildir
  useEffect(() => {
    if (webSocket && wsConnected && selectedGptPackage) {
      webSocket.send(JSON.stringify({ type: 'gpt_package_change', gpt_package_id: selectedGptPackage.id }));
    }
  }, [selectedGptPackage, webSocket, wsConnected]);

  // --- API Veri Çekme ---
  useEffect(() => {
    const fetchWhoAmI = async () => {
      setLoadingWhoAmI(true);
      try {
        const accessToken = localStorage.getItem('access_token');
        const response = await fetch(`${API_HOST}/api/auth/whoami/`, {
          headers: {
            'Authorization': `Bearer ${accessToken}`,
          },
        });
        if (!response.ok) {
          if (response.status === 401 || response.status === 403) {
            window.location.href = '/login';
            return;
          }
          throw new Error(`WhoAmI failed with status: ${response.status}`);
        }
        const data: WhoAmIResponse = await response.json();

        setUserInfo({
          fullname: data.current_profile?.user || data.username || 'Kullanıcı',
          avatar: data.current_profile?.avatar ?? undefined
        });
        
        const profilesData: UserProfileOption[] = (data.profiles || []).map((p) => ({
          value: p.id,
          label: p.company?.name
            ? `${p.company.name} - ${p.role?.name || 'Rol Yok'}`
            : p.role?.name || 'Genel Profil',
          gptPackages: (p.gpt_packages || []).map((pkg) => ({
            key: pkg.id,
            id: pkg.id, // Gerçek ID
            icon: <ExperimentOutlined />,
            label: pkg.name,
            is_default: pkg.is_default,
            description: pkg.description,
            group: pkg.group
          })),
          avatar: p.avatar ?? undefined
        }));
        setUserProfiles(profilesData);

        const currentProfData: UserProfileData | null = data.current_profile || (data.profiles && data.profiles.length > 0 ? data.profiles[0] : null);
        
        if (currentProfData) {
            // UserProfileOption tipine dönüştürme
            const currentProfOption: UserProfileOption = {
                value: currentProfData.id,
                label: currentProfData.company?.name ? `${currentProfData.company.name} - ${currentProfData.role?.name || 'Rol Yok'}` : currentProfData.role?.name || 'Genel Profil',
                gptPackages: (currentProfData.gpt_packages || []).map((pkg: any) => ({
                    key: pkg.id, id: pkg.id, label: pkg.name, is_default: pkg.is_default, icon: <ExperimentOutlined />, description: pkg.description, group: pkg.group
                })),
                avatar: currentProfData.avatar ?? undefined
            };

            setSelectedProfileId(currentProfOption.value);
            setGptPackages(currentProfOption.gptPackages || []);
            const defaultGpt = currentProfOption.gptPackages?.find(pkg => pkg.is_default) || currentProfOption.gptPackages?.[0];
            if (defaultGpt) {
                setSelectedGptPackage(defaultGpt);
            } else {
                setSelectedGptPackage(null);
            }
            setUserInfo(prev => ({
                ...(prev || {fullname: ''}),
                avatar: currentProfOption.avatar && typeof currentProfOption.avatar === 'string' ? currentProfOption.avatar : undefined
            }));
        } else {
            console.warn("No current profile found or no profiles available.");
            // Kullanıcıya bir profil seçmesi için yönlendirme veya uyarı
        }

      } catch (error) {
        console.error("Failed to fetch WhoAmI:", error);
        // window.location.href = '/login';
      } finally {
        setLoadingWhoAmI(false);
      }
    };
    fetchWhoAmI();
  }, []); // Sadece component mount olduğunda çalışsın

  // --- Olay Handler'ları ---
  const handleProfileChange = (value: string) => {
    const newProfile = userProfiles.find(p => p.value === value);
    if (newProfile) {
      setSelectedProfileId(newProfile.value);
      setUserInfo(prev => ({...(prev || {fullname: ''}), avatar: newProfile.avatar})); // Avatarı güncelle
      setGptPackages(newProfile.gptPackages || []);
      const defaultPkg = newProfile.gptPackages?.find(pkg => pkg.is_default) || newProfile.gptPackages?.[0];
      setSelectedGptPackage(defaultPkg || null);
      setMessages([]); // Profil değişince mesajları temizle
    }
  };

  const handleGptPackageChange = (menuInfo: { key: string }) => {
    const newPackage = gptPackages.find(p => p.key === menuInfo.key);
    if (newPackage && newPackage.id !== selectedGptPackage?.id) {
      setSelectedGptPackage(newPackage);
      setMessages([]); // Paket değişince mesajları temizle (isteğe bağlı)
    }
  };

  const handleNewChat = () => {
    if (webSocket && wsConnected) {
      console.log("Sending new_conversation request.");
      webSocket.send(JSON.stringify({ type: 'new_conversation' }));
    } else {
      message.warning("Yeni sohbet başlatmak için WebSocket bağlantısı gerekli.");
    }
    setMessages([]); // UI'da mesajları hemen temizle
  };

  const handleMessageInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setCurrentMessageInput(e.target.value);
  };

  const handleSendMessage = () => {
    const messageText = currentMessageInput.trim();
    if (!messageText) return;
    if (!wsConnected || !webSocket) {
      message.error("WebSocket bağlantısı aktif değil. Mesaj gönderilemedi.");
      return;
    }
    if (!selectedProfileId) {
        message.error("Lütfen önce bir kullanıcı profili seçin.");
        return;
    }
    if (!selectedGptPackage) {
        message.error("Lütfen önce bir GPT paketi seçin.");
        return;
    }

    // Kullanıcı mesajını UI'a ekle
    setMessages(prev => [...prev, {
      id: `user-${Date.now()}`,
      sender: 'user',
      content: messageText,
      timestamp: new Date()
    }]);

    console.log("Sending chat_message to WS:", messageText);
    webSocket.send(JSON.stringify({
      type: 'chat_message',
      message: messageText,
      // profile_id ve gpt_package_id backend consumer'da self'ten alınıyor,
      // ama yine de göndermek tutarlılık sağlayabilir veya consumer'daki mantığı basitleştirebilir.
      // Şimdiki consumer'ımız bunları beklemiyor, self'ten alıyor.
    }));
    
    setCurrentMessageInput('');
    setShowTypingIndicator(true); // Typing indicator'ı göster
    setIsSendingMessage(true); // Butonu pasif yapmak için (opsiyonel)
  };

  const handleLogout = async () => {
    try {
      const response = await fetch(`${API_HOST}/api/auth/logout/`, { 
          method: 'POST',
          headers: {
            // CSRF token gerekebilir, Django'nun SessionAuthentication'ı için
            // 'X-CSRFToken': getCookie('csrftoken'), // getCookie fonksiyonunu implemente etmeniz gerekir
          }
      });
      if (response.ok) {
        // Auth state'ini temizle (Context/localStorage vb.)
        // localStorage.removeItem('isAuthenticated'); // Basit örnek
        window.location.href = '/login';
      } else {
        message.error("Çıkış yapılamadı.");
      }
    } catch (error) {
      console.error("Logout failed:", error);
      message.error("Çıkış sırasında bir hata oluştu.");
    }
  };
  
  const userMenuProps: MenuProps = {
    items: [
      { key: 'profile', label: 'Kullanıcı Profili', icon: <UserOutlined /> /* onClick: () => navigate('/profile') */ },
      { key: 'settings', label: 'Ayarlar', icon: <SettingOutlined /> },
      { type: 'divider' },
      { key: 'logout', label: 'Çıkış Yap', icon: <LogoutOutlined />, danger: true, onClick: handleLogout },
    ]
  };

  if (loadingWhoAmI) {
    return (
      <Layout style={{ minHeight: '100vh', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
        <Spin size="large" fullscreen />
      </Layout>
    );
  }

  const currentGptPackageName = selectedGptPackage?.label || 'Paket Seçilmedi';

  return (
    <AntApp> {/* Ant Design message, notification, modal için context sağlar */}
      <Layout style={{ minHeight: '100vh' }}>
        <Header
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 32px',
            background: '#fff',
            borderBottom: '1px solid #f0f0f0',
            position: 'fixed',
            zIndex: 1,
            width: '100%',
            boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <Button
              type="text"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed(!collapsed)}
              style={{ fontSize: '16px', width: 48, height: 48, marginRight: 8 }}
            />
            <Text strong style={{ fontSize: '20px' }}>Hexense AI</Text>
            <Text type="secondary" style={{ marginLeft: 20, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 200 }} title={currentGptPackageName}>
                {currentGptPackageName}
            </Text>
          </div>
          
          <Space size="middle" align="center">
            <Select
              value={selectedProfileId}
              style={{ width: 220, minWidth: 150 }}
              onChange={handleProfileChange}
              options={userProfiles}
              placeholder="Profil Seçin"
              showSearch
              optionFilterProp="label"
              loading={loadingWhoAmI}
            />
            <Dropdown menu={userMenuProps} trigger={['click']}>
              <a onClick={(e) => e.preventDefault()} style={{ display: 'inline-flex', alignItems: 'center', height: '100%', padding: '0 8px' }}>
                <Space>
                  <Avatar icon={<UserOutlined />} src={userInfo?.avatar} size="small" />
                  <Text style={{maxWidth: 150, display: 'inline-block'}} ellipsis={{tooltip: userInfo?.fullname || 'Kullanıcı'}}>
                      {userInfo?.fullname || 'Kullanıcı'}
                  </Text>
                  <DownOutlined />
                </Space>
              </a>
            </Dropdown>
            <Button icon={<EditOutlined />} type="text" title="Canvas Alanını Aç/Kapat"/>
          </Space>
        </Header>
        <Layout style={{ paddingTop: 64 }}> {/* Header yüksekliği kadar padding */}
          <Sider
            collapsible
            collapsed={collapsed}
            onCollapse={(value) => setCollapsed(value)}
            theme="light"
            style={{
              borderRight: '1px solid #f0f0f0',
              height: 'calc(100vh - 64px)',
              position: 'fixed',
              left: 0,
              top: 64,
              bottom: 0,
              overflowY: 'auto',
              background: '#f7f8fc',
              boxShadow: '2px 0 8px rgba(0,0,0,0.03)',
            }}
          >
            <Button type="primary" icon={<PlusOutlined />} style={{ margin: '16px auto', display: 'block', width: collapsed ? 'auto' : 'calc(100% - 32px)' }} block={!collapsed} onClick={handleNewChat}>
              {!collapsed && 'Yeni Sohbet'}
            </Button>
            <Menu
              theme="light"
              mode="inline"
              selectedKeys={selectedGptPackage ? [selectedGptPackage.key] : []}
              onClick={handleGptPackageChange}
              items={gptPackages.length > 0 ? gptPackages.map(({is_default, ...item}) => item) : [{key: 'no-package', label: 'Paket Yok', disabled: true, icon: <ExperimentOutlined/>}]}
            />
          </Sider>
          <Layout style={{ marginLeft: collapsed ? 80 : 200, transition: 'margin-left 0.2s', display: 'flex', flexDirection: 'column', height: 'calc(100vh - 64px)', width: '100%' }}> {/* Sidebar genişliğine göre margin */}
            <Content
              style={{
                padding: '24px',
                margin: 0,
                background: '#f7f8fc',
                display: 'flex',
                flexDirection: 'column',
                flexGrow: 1,
                overflow: 'hidden'
              }}
            >
              <div ref={chatBoxRef} style={{ flexGrow: 1, background: '#fff', border: '1px solid #e8e8e8', borderRadius: 8, padding: 16, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '12px' }} id="chat-box-react">
                {(selectedGptPackage || gptPackages.length === 0) && (
                  <Alert
                    message="Lütfen önce bir GPT paketi seçin."
                    type="warning"
                    showIcon
                    style={{ marginBottom: 16 }}
                  />
                )}
                {messages.length === 0 && !showTypingIndicator && (
                    <div style={{textAlign: 'center', margin: 'auto', color: '#aaa'}}>
                        <MessageOutlined style={{fontSize: 48, marginBottom: 16}}/>
                        <Paragraph>Sohbet başlatmak için bir mesaj yazın veya kenar çubuğundan bir GPT paketi seçin.</Paragraph>
                    </div>
                )}
                {messages.map((msg) => (
                  <div key={msg.id} style={{ alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start', maxWidth: '70%' }}>
                    <div
                      style={{
                        padding: '12px 18px',
                        borderRadius: msg.sender === 'user' ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
                        background: msg.sender === 'user'
                          ? 'linear-gradient(90deg, #4f8cff 0%, #3358ff 100%)'
                          : '#f0f2f5',
                        color: msg.sender === 'user' ? 'white' : '#222',
                        boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
                        marginBottom: 8,
                        maxWidth: '75%',
                        alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                        fontSize: 16,
                        lineHeight: 1.6,
                      }}
                    >
                      {msg.sender === 'assistant' && msg.gptPackageName && (
                        <Text type="secondary" style={{ fontSize: '0.75rem', display: 'block', marginBottom: 4 }}>
                          {msg.gptPackageName}
                        </Text>
                      )}
                      {/* Stream bitene kadar metin, bitince parse edilmiş HTML */}
                      {msg.sender === 'assistant' && !msg.isStreaming ? (
                        <div className="markdown-content" dangerouslySetInnerHTML={{ __html: msg.content }} />
                      ) : (
                        <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{msg.content}</Paragraph>
                      )}
                       {msg.sender === 'system_error' && (
                        <Alert message={msg.content} type="error" style={{padding: '4px 8px'}}/>
                      )}
                    </div>
                    <Text type="secondary" style={{ fontSize: '0.7rem', display: 'block', textAlign: msg.sender === 'user' ? 'right' : 'left', marginTop: 2 }}>
                      {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </Text>
                  </div>
                ))}
                {showTypingIndicator && (
                    <div style={{ alignSelf: 'flex-start', maxWidth: '70%' }}>
                         <div style={{padding: '8px 12px', borderRadius: '12px', background: '#e8e8e8', color: 'black', borderBottomLeftRadius: '0px'}}>
                            {selectedGptPackage && <Text type="secondary" style={{ fontSize: '0.75rem', display: 'block', marginBottom: 4 }}>{selectedGptPackage.label}</Text>}
                            <LoadingOutlined style={{ fontSize: 18, color: '#1890ff' }} />
                         </div>
                    </div>
                )}
              </div>
              <div style={{ marginTop: 16, padding: '16px', background: '#fff', border: '1px solid #e8e8e8', borderRadius: 8}} id="message-input-react">
                <Space.Compact
                  style={{
                    width: '100%',
                    background: '#fff',
                    borderRadius: 16,
                    boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
                    padding: 4,
                  }}
                >
                  <Input.TextArea
                    placeholder="Bir mesaj yazın..."
                    autoSize={{ minRows: 1, maxRows: 5 }}
                    value={currentMessageInput}
                    onChange={handleMessageInputChange}
                    onPressEnter={(e) => {
                      if (!e.shiftKey) {
                        e.preventDefault();
                        handleSendMessage();
                      }
                    }}
                    disabled={isSendingMessage}
                    style={{
                      border: 'none',
                      borderRadius: 16,
                      fontSize: 16,
                      background: 'transparent',
                      resize: 'none',
                      boxShadow: 'none',
                    }}
                  />
                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    onClick={handleSendMessage}
                    loading={isSendingMessage}
                    disabled={isSendingMessage}
                    style={{
                      borderRadius: 16,
                      marginLeft: 8,
                      height: 48,
                      width: 48,
                      fontSize: 20,
                      boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
                    }}
                  />
                </Space.Compact>
              </div>
            </Content>
          </Layout>
        </Layout>
      </Layout>
    </AntApp>
  );
};

export default ChatPage;