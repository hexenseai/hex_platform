// frontend/src/pages/ChatPage.tsx

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box, AppBar, Toolbar, Typography, IconButton, Drawer, Button, Avatar, Select, MenuItem, Alert, CircularProgress, Snackbar, TextField, Paper, FormControl, InputLabel, useMediaQuery
} from '@mui/material';
import type { SelectChangeEvent } from '@mui/material';
import {
  Menu as MenuIcon,
  Add as AddIcon,
  Send as SendIcon,
  Person as PersonIcon,
  Logout as LogoutIcon,
  Science as ScienceIcon,
  Chat as ChatIcon,
  HourglassEmpty as HourglassEmptyIcon,
  Close as CloseIcon
} from '@mui/icons-material';
import { marked } from 'marked';
import type {
  UserInfo,
  GptPackageOption,
  UserProfileData,
  WhoAmIResponse,
  UserProfileOption,
  ChatMessage
} from '../types';
import { useTheme, createTheme, ThemeProvider } from '@mui/material/styles';

// Marked ayarları
marked.setOptions({
  breaks: true,
  gfm: true,
});

// Dark mode theme
const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    background: {
      default: '#1a1b1e',
      paper: '#242528',
    },
    primary: { main: '#8ab4f8' },
    text: { primary: '#e3e3e3', secondary: '#9aa0a6' },
    divider: '#35363a',
  },
  shape: { borderRadius: 12 },
  typography: {
    fontFamily: 'Google Sans, Roboto, Arial, sans-serif',
    fontSize: 16,
  },
});

const SIDEBAR_WIDTH_OPEN = 280;
const SIDEBAR_WIDTH_CLOSED = 0; // Tamamen gizli sidebar
const CHAT_MAX_WIDTH = 800; // Daha geniş chat alanı

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
  const webSocketRef = useRef<WebSocket | null>(null);
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [showTypingIndicator, setShowTypingIndicator] = useState<boolean>(false);
  const [snackbar, setSnackbar] = useState<{open: boolean, message: string, severity: 'success'|'error'|'warning'|'info'}>({open: false, message: '', severity: 'info'});
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

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
  useEffect(() => {
    const accessToken = localStorage.getItem('access_token');
    if (!accessToken) {
      setSnackbar({open: true, message: 'Access token bulunamadı. Lütfen tekrar giriş yapın.', severity: 'error'});
        return;
    }
    const wsUrl = `${API_WS_HOST}/ws/chat/?token=${accessToken}`;
    const ws = new WebSocket(wsUrl);
    webSocketRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
      if (selectedProfileId) {
        ws.send(JSON.stringify({ type: 'profile_change', profile_id: selectedProfileId }));
      }
      if (selectedGptPackage) {
        ws.send(JSON.stringify({ type: 'gpt_package_change', gpt_package_id: selectedGptPackage.id }));
      }
      setSnackbar({open: true, message: 'Bağlantı kuruldu!', severity: 'success'});
    };

    ws.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data as string);
      } catch (e) {
        return;
      }
      switch (data.type) {
        case 'connection_established':
          setSnackbar({open: true, message: data.message || 'Bağlantı kuruldu!', severity: 'success'});
          break;
        case 'profile_change_ack':
          const ackProfile = userProfiles.find(p => p.value === data.profile_id);
          if (ackProfile) {
            setGptPackages(ackProfile.gptPackages || []);
            const defaultPkg = ackProfile.gptPackages?.find(pkg => pkg.is_default) || ackProfile.gptPackages?.[0];
            if (defaultPkg && webSocketRef.current) {
                webSocketRef.current.send(JSON.stringify({ type: 'gpt_package_change', gpt_package_id: defaultPkg.id }));
                setSelectedGptPackage(defaultPkg);
            } else if (ackProfile.gptPackages && ackProfile.gptPackages.length > 0 && webSocketRef.current) {
                webSocketRef.current.send(JSON.stringify({ type: 'gpt_package_change', gpt_package_id: ackProfile.gptPackages[0].id }));
                setSelectedGptPackage(ackProfile.gptPackages[0]);
            } else {
                setSelectedGptPackage(null);
            }
          }
          break;
        case 'gpt_package_change_ack':
          setCurrentConversationId(data.conversation_id);
          setMessages([]);
          break;
        case 'new_conversation_ack':
          setCurrentConversationId(data.conversation_id);
          setMessages([]);
          break;
        case 'assistant_message_chunk':
          setShowTypingIndicator(false);
          setMessages(prevMessages => {
            const lastMessage = prevMessages[prevMessages.length - 1];
            if (lastMessage && lastMessage.sender === 'assistant' && lastMessage.isStreaming) {
              return [
                ...prevMessages.slice(0, -1),
                { ...lastMessage, content: lastMessage.content + data.chunk }
              ];
            } else {
              return [
                ...prevMessages,
                {
                  id: `asst-${Date.now()}`,
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
           setShowTypingIndicator(false);
           setIsSendingMessage(false);
           setMessages(prevMessages => {
            const lastMessage = prevMessages[prevMessages.length - 1];
            if (lastMessage && lastMessage.sender === 'assistant' && lastMessage.isStreaming) {
              return [
                ...prevMessages.slice(0, -1),
                { ...lastMessage, isStreaming: false, content: marked.parse(lastMessage.content) as string }
              ];
            }
            return prevMessages;
          });
           break;
        case 'ui_actions':
          setSnackbar({open: true, message: 'UI Aksiyonu Alındı', severity: 'info'});
          break;
        case 'error':
          setShowTypingIndicator(false);
          setMessages(prev => [...prev, {
            id: `err-${Date.now()}`, sender: 'system_error', content: `Hata: ${data.message}`, timestamp: new Date()
          }]);
          setSnackbar({open: true, message: `Sunucu Hatası: ${data.message}`, severity: 'error'});
          break;
        default:
          break;
      }
    };

    ws.onclose = (event) => {
      setWsConnected(false);
      webSocketRef.current = null;
      if (event.code !== 1000) {
        setSnackbar({open: true, message: 'Bağlantı kesildi. 5 saniye içinde yeniden deneniyor...', severity: 'error'});
        setTimeout(() => {
          // Bağlantı tekrar kurulacak
          window.location.reload(); // En güvenli yol: sayfayı yenilemek
        }, 5000);
      }
    };

    ws.onerror = () => {
      setSnackbar({open: true, message: 'WebSocket bağlantı hatası oluştu.', severity: 'error'});
    };

    return () => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close(1000, 'Component unmounting');
      }
      webSocketRef.current = null;
      setWsConnected(false);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (webSocketRef.current && wsConnected && selectedProfileId) {
      webSocketRef.current.send(JSON.stringify({ type: 'profile_change', profile_id: selectedProfileId }));
    }
  }, [selectedProfileId, wsConnected]);

  useEffect(() => {
    if (webSocketRef.current && wsConnected && selectedGptPackage) {
      webSocketRef.current.send(JSON.stringify({ type: 'gpt_package_change', gpt_package_id: selectedGptPackage.id }));
    }
  }, [selectedGptPackage, wsConnected]);

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
            id: pkg.id,
            icon: <ScienceIcon />,
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
            const currentProfOption: UserProfileOption = {
                value: currentProfData.id,
                label: currentProfData.company?.name ? `${currentProfData.company.name} - ${currentProfData.role?.name || 'Rol Yok'}` : currentProfData.role?.name || 'Genel Profil',
                gptPackages: (currentProfData.gpt_packages || []).map((pkg: any) => ({
                    key: pkg.id, id: pkg.id, label: pkg.name, is_default: pkg.is_default, icon: <ScienceIcon />, description: pkg.description, group: pkg.group
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
        }
      } catch (error) {
        setSnackbar({open: true, message: 'Kullanıcı bilgisi alınamadı.', severity: 'error'});
      } finally {
        setLoadingWhoAmI(false);
      }
    };
    fetchWhoAmI();
  }, []);

  const handleProfileChange = (event: SelectChangeEvent<string>) => {
    const value = event.target.value;
    const newProfile = userProfiles.find(p => p.value === value);
    if (newProfile) {
      setSelectedProfileId(newProfile.value);
      setUserInfo(prev => ({...(prev || {fullname: ''}), avatar: newProfile.avatar}));
      setGptPackages(newProfile.gptPackages || []);
      const defaultPkg = newProfile.gptPackages?.find(pkg => pkg.is_default) || newProfile.gptPackages?.[0];
      setSelectedGptPackage(defaultPkg || null);
      setMessages([]);
    }
  };

  const handleGptPackageChange = (event: SelectChangeEvent<string>) => {
    const value = event.target.value;
    const newPackage = gptPackages.find(p => p.key === value);
    if (newPackage && newPackage.id !== selectedGptPackage?.id) {
      setSelectedGptPackage(newPackage);
      setMessages([]);
    }
  };

  const handleNewChat = () => {
    if (webSocketRef.current && wsConnected) {
      webSocketRef.current.send(JSON.stringify({ type: 'new_conversation' }));
      setMessages([]);
    } else {
      setSnackbar({open: true, message: 'Yeni sohbet başlatmak için WebSocket bağlantısı gerekli.', severity: 'warning'});
    }
  };

  const handleMessageInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setCurrentMessageInput(e.target.value);
  };

  const handleSendMessage = () => {
    const messageText = currentMessageInput.trim();
    if (!messageText) return;
    if (!wsConnected || !webSocketRef.current) {
      setSnackbar({open: true, message: 'WebSocket bağlantısı aktif değil. Mesaj gönderilemedi.', severity: 'error'});
      return;
    }
    if (!selectedProfileId) {
      setSnackbar({open: true, message: 'Lütfen önce bir kullanıcı profili seçin.', severity: 'error'});
        return;
    }
    if (!selectedGptPackage) {
      setSnackbar({open: true, message: 'Lütfen önce bir GPT paketi seçin.', severity: 'error'});
        return;
    }
    setMessages(prev => [...prev, {
      id: `user-${Date.now()}`,
      sender: 'user',
      content: messageText,
      timestamp: new Date()
    }]);
    webSocketRef.current.send(JSON.stringify({
      type: 'chat_message',
      message: messageText,
    }));
    setCurrentMessageInput('');
    setShowTypingIndicator(true);
    setIsSendingMessage(true);
  };

  const handleLogout = async () => {
    try {
      const response = await fetch(`${API_HOST}/api/auth/logout/`, { method: 'POST' });
      if (response.ok) {
        window.location.href = '/login';
      } else {
        setSnackbar({open: true, message: 'Çıkış yapılamadı.', severity: 'error'});
      }
    } catch (error) {
      setSnackbar({open: true, message: 'Çıkış sırasında bir hata oluştu.', severity: 'error'});
    }
  };

  // Responsive: Mobilde sidebar kapalı başlasın
  useEffect(() => {
    if (isMobile) setSidebarOpen(false);
    else setSidebarOpen(true);
  }, [isMobile]);

  if (loadingWhoAmI) {
    return (
      <Box sx={{ minHeight: '100vh', display: 'flex', justifyContent: 'center', alignItems: 'center', bgcolor: '#f5f6fa' }}>
        <CircularProgress size={80} />
      </Box>
    );
  }

  const currentGptPackageName = selectedGptPackage?.label || 'Paket Seçilmedi';

  return (
    <ThemeProvider theme={darkTheme}>
      <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
        {/* Sidebar */}
        <Drawer
          variant={isMobile ? 'temporary' : 'permanent'}
          open={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          PaperProps={{
            sx: {
              width: SIDEBAR_WIDTH_OPEN,
              bgcolor: 'background.paper',
              borderRight: '1px solid',
              borderColor: 'divider',
              boxShadow: 'none',
              p: 2,
            }
          }}
        >
          {/* Logo alanı */}
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: sidebarOpen ? 'flex-start' : 'center', height: 64, px: 2, borderBottom: 'none', width: '100%' }}>
            <ChatIcon color="primary" sx={{ fontSize: 32, mr: sidebarOpen ? 1.5 : 0, transition: 'margin 0.2s' }} />
            {sidebarOpen && <Typography variant="h6" fontWeight={700} color="primary">Hexense AI</Typography>}
            {(!isMobile && sidebarOpen) && (
              <IconButton size="small" onClick={() => setSidebarOpen(false)} sx={{ ml: 'auto', color: 'text.secondary' }}>
                <CloseIcon />
              </IconButton>
            )}
          </Box>
          {/* Seçim kutuları ve butonlar */}
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: sidebarOpen ? 'flex-start' : 'center', gap: 2, width: '100%', mt: 3, px: sidebarOpen ? 2 : 0 }}>
            <FormControl size="small" fullWidth={sidebarOpen} sx={{ bgcolor: '#23262F', borderRadius: 2, minWidth: sidebarOpen ? 160 : 48 }}>
              <Select
                value={selectedProfileId || ''}
                onChange={handleProfileChange}
                displayEmpty
                renderValue={selected => {
                  const profile = userProfiles.find(p => p.value === selected);
                  return profile ? (
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Avatar src={profile.avatar} sx={{ width: 24, height: 24 }} />
                      {sidebarOpen && <Typography variant="body2">{profile.label}</Typography>}
                    </Box>
                  ) : <Typography variant="body2" color="text.secondary">Profil Seçin</Typography>;
                }}
                sx={{ '.MuiSelect-select': { p: 0.5, display: 'flex', alignItems: 'center', justifyContent: sidebarOpen ? 'flex-start' : 'center', color: 'text.primary' } }}
              >
                {userProfiles.map(profile => (
                  <MenuItem key={profile.value} value={profile.value} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Avatar src={profile.avatar} sx={{ width: 24, height: 24, mr: 1 }} />
                    <Typography variant="body2">{profile.label}</Typography>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl size="small" fullWidth={sidebarOpen} sx={{ bgcolor: '#23262F', borderRadius: 2, minWidth: sidebarOpen ? 160 : 48 }}>
              <Select
                value={selectedGptPackage?.key || ''}
                onChange={handleGptPackageChange}
                displayEmpty
                renderValue={selected => {
                  const pkg = gptPackages.find(p => p.key === selected);
                  return pkg ? (
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <ScienceIcon color="primary" />
                      {sidebarOpen && <Typography variant="body2">{pkg.label}</Typography>}
                    </Box>
                  ) : <Typography variant="body2" color="text.secondary">GPT Paketi Seçin</Typography>;
                }}
                sx={{ '.MuiSelect-select': { p: 0.5, display: 'flex', alignItems: 'center', justifyContent: sidebarOpen ? 'flex-start' : 'center', color: 'text.primary' } }}
              >
                {gptPackages.map(pkg => (
                  <MenuItem key={pkg.key} value={pkg.key} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <ScienceIcon color="primary" sx={{ mr: 1 }} />
                    <Typography variant="body2">{pkg.label}</Typography>
                  </MenuItem>
                ))}
                {gptPackages.length === 0 && <MenuItem value="" disabled>Paket Yok</MenuItem>}
              </Select>
            </FormControl>
            <Button
              variant="contained"
              color="primary"
              sx={{ borderRadius: '50%', minWidth: 0, width: 48, height: 48, boxShadow: 2, alignSelf: sidebarOpen ? 'flex-start' : 'center', bgcolor: '#23262F', color: 'primary.main', '&:hover': { bgcolor: '#23262F', color: 'primary.light' } }}
              onClick={handleNewChat}
            >
              <AddIcon />
              {sidebarOpen && <Typography variant="body2" sx={{ ml: 1, fontWeight: 500 }}>Yeni Sohbet</Typography>}
            </Button>
          </Box>
          <Box sx={{ flexGrow: 1 }} />
          <Box sx={{ display: 'flex', flexDirection: sidebarOpen ? 'row' : 'column', alignItems: 'center', justifyContent: 'center', width: '100%', mb: 2, gap: 1 }}>
            <Avatar src={userInfo?.avatar} sx={{ width: 40, height: 40 }} />
            {sidebarOpen && <Typography variant="body2" sx={{ ml: 1 }}>{userInfo?.fullname || 'Kullanıcı'}</Typography>}
            <IconButton color="default" onClick={handleLogout} title="Çıkış Yap">
              <LogoutIcon />
            </IconButton>
          </Box>
        </Drawer>
        {/* Ana içerik */}
        <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: '100vh', position: 'relative', bgcolor: 'background.default' }}>
          {/* AppBar'ın yüksekliği kadar üstten boşluk */}
          <Toolbar />
          {/* Chat akışı alanı */}
          <Box
            sx={{
              flex: 1,
              width: '100%',
              maxWidth: { xs: '100%', md: 1200 },
              mx: 'auto',
              px: { xs: 1, sm: 2, md: 4 },
              pb: { xs: 2, sm: 3, md: 4 },
              pt: 2,
              overflowY: 'auto',
              display: 'flex',
              flexDirection: 'column',
              gap: 3,
            }}
          >
            {/* Paket seçilmediyse uyarı */}
            {(!selectedGptPackage && gptPackages.length === 0) && (
              <Alert severity="warning" sx={{ mb: 2 }}>Lütfen önce bir GPT paketi seçin.</Alert>
            )}
            {/* Boş chat ekranı */}
            {messages.length === 0 && !showTypingIndicator && (
              <Box sx={{ textAlign: 'center', color: '#bbb', my: 6 }}>
                <ChatIcon sx={{ fontSize: 56, mb: 2 }} />
                <Typography variant="h5" fontWeight={500}>Sohbet başlatmak için bir mesaj yazın</Typography>
                <Typography variant="body2" color="text.secondary">veya kenar çubuğundan bir GPT paketi seçin.</Typography>
              </Box>
            )}
            {/* Mesajlar */}
            {messages.map((msg) => (
              msg.sender === 'user' ? (
                <Box
                  key={msg.id}
                  sx={{
                    display: 'flex',
                    flexDirection: 'row-reverse',
                    gap: 2,
                    maxWidth: '85%',
                    ml: 'auto',
                  }}
                >
                  <Avatar 
                    sx={{ 
                      width: 32, 
                      height: 32,
                      bgcolor: 'primary.main',
                      color: 'background.paper',
                    }}
                  >
                    <PersonIcon />
                  </Avatar>
                  <Paper
                    sx={{
                      p: 2,
                      bgcolor: 'background.paper',
                      borderRadius: '16px 16px 4px 16px',
                      border: '1px solid',
                      borderColor: 'divider',
                      boxShadow: 'none',
                    }}
                  >
                    <Typography>{msg.content}</Typography>
                  </Paper>
                </Box>
              ) : (
                <Box
                  key={msg.id}
                  sx={{
                    display: 'flex',
                    gap: 2,
                    maxWidth: '85%',
                  }}
                >
                  <Avatar
                    sx={{
                      width: 32,
                      height: 32,
                      bgcolor: 'primary.main',
                      color: 'background.paper',
                    }}
                  >
                    <ScienceIcon />
                  </Avatar>
                  <Paper
                    sx={{
                      p: 2,
                      bgcolor: 'background.paper',
                      borderRadius: '16px 16px 16px 4px',
                      border: '1px solid',
                      borderColor: 'divider',
                      boxShadow: 'none',
                    }}
                  >
                    <Typography
                      className="markdown-content"
                      dangerouslySetInnerHTML={{ __html: msg.content }}
                    />
                  </Paper>
                </Box>
              )
            ))}
            {/* Asistan yazıyor animasyonu */}
            {showTypingIndicator && (
              <Box sx={{ display: 'flex', flexDirection: 'row', alignItems: 'flex-end', gap: 1.5, width: '100%' }}>
                <Avatar sx={{ width: 32, height: 32, bgcolor: '#23262F', color: 'primary.main', fontWeight: 700 }}>
                  <ScienceIcon />
                </Avatar>
                <Box sx={{ flex: 1, px: 0, py: 0, bgcolor: 'transparent', color: '#fff', fontSize: 16, lineHeight: 1.7, maxWidth: '100%', wordBreak: 'break-word', borderRadius: 0, display: 'flex', alignItems: 'center', gap: 1 }}>
                  {selectedGptPackage && <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mr: 1 }}>{selectedGptPackage.label}</Typography>}
                  <HourglassEmptyIcon sx={{ fontSize: 18, color: 'primary.main' }} />
                </Box>
              </Box>
            )}
          </Box>
          {/* Chat formu: sabit, ekranın en altında, responsive padding ve genişlik */}
          <Paper
            elevation={0}
            sx={{
              position: 'sticky',
              bottom: 0,
              p: 2,
              bgcolor: 'background.default',
              borderTop: '1px solid',
              borderColor: 'divider',
            }}
          >
            <Box
              sx={{
                maxWidth: CHAT_MAX_WIDTH,
                mx: 'auto',
                display: 'flex',
                gap: 2,
              }}
            >
              <TextField
                fullWidth
                multiline
                maxRows={4}
                placeholder="Mesajınızı yazın..."
                value={currentMessageInput}
                onChange={handleMessageInputChange}
                variant="outlined"
                sx={{
                  '& .MuiOutlinedInput-root': {
                    bgcolor: 'background.paper',
                    borderRadius: 2,
                  }
                }}
              />
              <IconButton
                onClick={handleSendMessage}
                disabled={isSendingMessage}
                sx={{
                  bgcolor: 'primary.main',
                  color: 'background.paper',
                  '&:hover': {
                    bgcolor: 'primary.dark',
                  }
                }}
              >
                <SendIcon />
              </IconButton>
            </Box>
          </Paper>
        </Box>
      </Box>
    </ThemeProvider>
  );
};

export default ChatPage;