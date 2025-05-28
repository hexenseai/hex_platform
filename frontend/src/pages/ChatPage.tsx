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
  Close as CloseIcon,
  Mic as MicIcon,
  CameraAlt as CameraAltIcon,
  ChevronLeft as ChevronLeftIcon,
  ChevronRight as ChevronRightIcon,
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
import DOMPurify from 'dompurify';
import logoOnly from '../assets/logo/logo_only.png';
import logoFull from '../assets/logo/logo_full.png';

// Marked ayarları
marked.setOptions({
  breaks: true,
  gfm: true,
});

const SIDEBAR_WIDTH = 280;
const SIDEBAR_COLLAPSED_WIDTH = 64;

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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
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

  // Sidebar genişliğini hesaplayan yardımcı fonksiyon
  const getSidebarWidth = () => {
    if (isMobile) return 0;
    return sidebarCollapsed ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_WIDTH;
  };

  return (
    <Box sx={{ 
      display: 'flex', 
      minHeight: '100vh',
      width: '100vw',
      bgcolor: theme => theme.palette.background.customBackground
    }}>
      {/* Drawer */}
      <Drawer
        variant={isMobile ? 'temporary' : 'permanent'}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        sx={{
          width: getSidebarWidth(),
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width: getSidebarWidth(),
            boxSizing: 'border-box',
            bgcolor: 'background.default',
            borderRight: 'none',
            overflowX: 'hidden',
            transition: theme => theme.transitions.create('width', {
              easing: theme.transitions.easing.sharp,
              duration: theme.transitions.duration.enteringScreen,
            }),
          },
        }}
      >
        {/* Logo Area */}
        <Box sx={{ 
          p: 2, 
          display: 'flex', 
          alignItems: 'center', 
          gap: 1,
          justifyContent: sidebarCollapsed ? 'center' : 'space-between'
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {sidebarCollapsed ? (
              <img src={logoOnly} alt="Logo" style={{ height: 40 }} />
            ) : (
              <img src={logoFull} alt="Logo with text" style={{ height: 40 }} />
            )}
          </Box>
          {!isMobile && (
            <IconButton 
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              sx={{ display: sidebarCollapsed ? 'none' : 'flex' }}
            >
              <ChevronLeftIcon />
            </IconButton>
          )}
        </Box>

        {/* User Profile & Logout */}
        <Box sx={{ mt: 'auto', p: 2, borderTop: 1, borderColor: 'divider' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Avatar 
              src={userInfo?.avatar}
              sx={{ width: 32, height: 32 }}
            />
            {!sidebarCollapsed && (
              <>
                <Box sx={{ flex: 1 }}>
                  <Typography variant="subtitle2">{userInfo?.fullname}</Typography>
                </Box>
                <IconButton onClick={handleLogout} size="small">
                  <LogoutIcon />
                </IconButton>
              </>
            )}
          </Box>
        </Box>
      </Drawer>

      {/* Main Content */}
      <Box sx={{ 
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        width: '100%',
        bgcolor: theme => theme.palette.background.default,
        position: 'relative',
        minHeight: '100vh',
        pb: { xs: 10, sm: 12 }, // Chat formun yüksekliği kadar padding
      }}>
        {/* AppBar */}
        <AppBar 
          position="sticky" 
          elevation={0}
          sx={{ 
            bgcolor: theme => theme.palette.background.customBackground,
            zIndex: 1100,
            boxShadow: 'none',
            border: 'none',
          }}
        >
          <Toolbar>
            {isMobile ? (
              <IconButton edge="start" onClick={() => setSidebarOpen(true)}>
                <MenuIcon />
              </IconButton>
            ) : (
              sidebarCollapsed && (
                <IconButton edge="start" onClick={() => setSidebarCollapsed(false)}>
                  <ChevronRightIcon />
                </IconButton>
              )
            )}
            {/* Profile & Package Selectors */}
            <Box sx={{ display: 'flex', gap: 2, flex: 1, justifyContent: 'center' }}>
              <FormControl size="small" sx={{ minWidth: 200 }}>
                <Select
                  value={selectedProfileId || ''}
                  onChange={handleProfileChange}
                  variant="outlined"
                  sx={{
                    borderRadius: '999px',
                    background: theme => theme.palette.background.paper,
                    boxShadow: 2,
                    border: 'none',
                    '& .MuiOutlinedInput-notchedOutline': {
                      border: 'none',
                    },
                    '& .MuiSelect-select': {
                      borderRadius: '999px',
                      background: theme => theme.palette.background.paper,
                      px: 2,
                    },
                  }}
                  MenuProps={{
                    PaperProps: {
                      sx: {
                        borderRadius: '16px',
                        boxShadow: 4,
                        bgcolor: theme => theme.palette.background.paper,
                      }
                    }
                  }}
                >
                  {userProfiles.map(profile => (
                    <MenuItem key={profile.value} value={profile.value}>
                      {profile.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 200 }}>
                <Select
                  value={selectedGptPackage?.key || ''}
                  onChange={handleGptPackageChange}
                  variant="outlined"
                  sx={{
                    borderRadius: '999px',
                    background: theme => theme.palette.background.paper,
                    boxShadow: 2,
                    border: 'none',
                    '& .MuiOutlinedInput-notchedOutline': {
                      border: 'none',
                    },
                    '& .MuiSelect-select': {
                      borderRadius: '999px',
                      background: theme => theme.palette.background.paper,
                      px: 2,
                    },
                  }}
                  MenuProps={{
                    PaperProps: {
                      sx: {
                        borderRadius: '16px',
                        boxShadow: 4,
                        bgcolor: theme => theme.palette.background.paper,
                      }
                    }
                  }}
                >
                  {gptPackages.map(pkg => (
                    <MenuItem key={pkg.key} value={pkg.key}>
                      {pkg.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Box>
          </Toolbar>
        </AppBar>

        {/* Chat Messages */}
        <Box 
          ref={chatBoxRef}
          sx={{ 
            flex: 1, 
            width: '100%',
            overflowY: 'auto',
            bgcolor: theme => theme.palette.background.customBackground,
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
            px: { xs: 2, sm: 4, md: 6 },
            py: 3,
            maxWidth: '100vw',
            boxSizing: 'border-box',
            // Chat formun yüksekliği kadar alt padding bırak
            pb: { xs: 10, sm: 12 },
          }}
        >
          <Box sx={{
            width: '100%',
            maxWidth: '1200px',
            mx: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
          }}>
            {messages.map(msg => (
              <Box
                key={msg.id}
                className="message-container"
                sx={{
                  display: 'flex',
                  flexDirection: msg.sender === 'user' ? 'row-reverse' : 'row',
                  gap: 2,
                  width: '100%',
                  '& > .MuiBox-root': {
                    maxWidth: msg.sender === 'user' ? '70%' : '100%',
                  }
                }}
              >
                <Avatar
                  sx={{
                    width: 32,
                    height: 32,
                    bgcolor: msg.sender === 'user' ? 'primary.main' : 'background.paper',
                    flexShrink: 0,
                  }}
                >
                  {msg.sender === 'user' ? <PersonIcon /> : <ScienceIcon />}
                </Avatar>
                <Box sx={{ flex: 1 }}>
                  {msg.sender === 'assistant' && (
                    <Typography variant="caption" color="text.secondary">
                      {msg.gptPackageName} • {new Date(msg.timestamp).toLocaleTimeString()}
                    </Typography>
                  )}
                  <Paper
                    sx={{
                      p: 2,
                      mt: 0.5,
                      bgcolor: msg.sender === 'user' ? 'primary.main' : 'background.paper',
                      color: msg.sender === 'user' ? 'background.paper' : 'text.primary',
                      borderRadius: msg.sender === 'user' ? '20px 20px 4px 20px' : '20px 20px 20px 4px',
                      boxShadow: 'none',
                      border: 'none',
                    }}
                  >
                    {msg.sender === 'assistant' ? (
                      <div
                        dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(msg.content) }}
                      />
                    ) : (
                      <Typography>{msg.content}</Typography>
                    )}
                  </Paper>
                </Box>
              </Box>
            ))}
          </Box>
        </Box>

        {/* Chat Input - Sabit Alt Form */}
        <Box
          sx={{
            position: 'fixed',
            left: { xs: 0, sm: getSidebarWidth() },
            bottom: 0,
            width: { xs: '100vw', sm: `calc(100vw - ${getSidebarWidth()}px)` },
            bgcolor: theme => theme.palette.background.customBackground,
            zIndex: 1200,
            boxShadow: 'none',
            px: { xs: 2, sm: 4, md: 6 },
            py: 2,
            maxWidth: '100vw',
          }}
        >
          <Box sx={{ 
            maxWidth: '1200px',
            mx: 'auto',
          }}>
            <TextField
              fullWidth
              multiline
              maxRows={4}
              placeholder="Mesajınızı yazın..."
              value={currentMessageInput}
              onChange={handleMessageInputChange}
              variant="outlined"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSendMessage();
                }
              }}
              sx={{
                '& .MuiOutlinedInput-root': {
                  bgcolor: 'background.paper',
                }
              }}
            />
            <Box sx={{
              display: 'flex',
              gap: 1,
              alignItems: 'center',
              justifyContent: 'flex-end',
              mt: 1,
              p: 1,
              bgcolor: 'background.default',
              borderRadius: 2,
              boxShadow: 1,
            }}>
              <IconButton size="small" onClick={handleNewChat}>
                <AddIcon fontSize="small" />
              </IconButton>
              <IconButton size="small">
                <MicIcon fontSize="small" />
              </IconButton>
              <IconButton size="small">
                <CameraAltIcon fontSize="small" />
              </IconButton>
              <IconButton 
                size="small"
                onClick={handleSendMessage}
                disabled={!currentMessageInput.trim()}
                color="primary"
              >
                <SendIcon fontSize="small" />
              </IconButton>
            </Box>
          </Box>
        </Box>
      </Box>
    </Box>
  );
};

export default ChatPage;