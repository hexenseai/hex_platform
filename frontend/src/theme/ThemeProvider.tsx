import { createTheme, ThemeProvider as MuiThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { grey, blue } from '@mui/material/colors';

// Tema tipini genişlet
declare module '@mui/material/styles' {
  interface TypeBackground {
    chat?: string;
    customBackground?: string;
  }
}

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: blue[300],
      light: blue[200],
      dark: blue[400],
    },
    background: {
      default: grey[900],
      paper: grey[800],
      chat: '#1B232A',
      customBackground: '#202B38',
    },
    text: {
      primary: grey[100],
      secondary: grey[400],
    },
    divider: grey[700],
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundColor: grey[800],
          color: grey[100],
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: grey[500],
          borderBottom: `1px solid ${grey[700]}`,
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          backgroundColor: grey[900],
          borderRight: `1px solid ${grey[700]}`,
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
        },
      },
    },
    MuiTextField: {
      defaultProps: {
        variant: 'outlined',
      },
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-root': {
            backgroundColor: grey[800],
          },
        },
      },
    },
  },
  shape: {
    borderRadius: 12,
  },
  typography: {
    fontFamily: '"Google Sans", "Roboto", "Arial", sans-serif',
    h1: { fontWeight: 500 },
    h2: { fontWeight: 500 },
    h3: { fontWeight: 500 },
    h4: { fontWeight: 500 },
    h5: { fontWeight: 500 },
    h6: { fontWeight: 500 },
  },
});

interface ThemeProviderProps {
  children: React.ReactNode;
}

export const ThemeProvider: React.FC<ThemeProviderProps> = ({ children }) => {
  return (
    <MuiThemeProvider theme={theme}>
      <CssBaseline />
      {children}
    </MuiThemeProvider>
  );
};