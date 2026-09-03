//@ts-nocheck
import axios from 'axios';

// const FLASK_API_URL = 'http://44.213.80.217:8000'
// const FLASK_API_URL = process.env.NEXT_PUBLIC_FLASK_API_URL || 'http://127.0.0.1:8000';
const FLASK_API_URL = "PLACE_HOLDER";

// Validate that the API URL uses HTTPS in production
const validateApiUrl = (url: string): void => {
  if (url && url !== "PLACE_HOLDER") {
    const urlLower = url.toLowerCase();
    // Allow localhost and 127.0.0.1 for development
    const isLocalhost = urlLower.includes('localhost') || urlLower.includes('127.0.0.1');
    
    if (!isLocalhost && !urlLower.startsWith('https://')) {
      console.error('Security Error: API URL must use HTTPS in production environment');
      console.error('Insecure URL detected:', url);
      throw new Error('API URL must use HTTPS. Refusing to send credentials over insecure connection.');
    }
  }
};

// Validate the API URL on initialization
try {
  validateApiUrl(FLASK_API_URL);
} catch (error) {
  console.error('Failed to initialize API client:', error);
}

// export const orcaApi = axios.create({
//   baseURL: FLASK_API_URL,
//   timeout: 1000,
//   headers: {
//     'Content-Type': 'application/json',
//   },
// });
export const getToken = () => {
  if (typeof window !== 'undefined') {
    return localStorage.getItem('token');
  }
  return null;
};

export const orcaApi = axios.create({
  baseURL: FLASK_API_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

orcaApi.interceptors.request.use(
  config => {
    // Re-validate HTTPS before each request
    if (config.baseURL) {
      try {
        validateApiUrl(config.baseURL);
      } catch (error) {
        console.error('Request blocked due to insecure URL');
        return Promise.reject(error);
      }
    }
    
    const token = getToken();
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    return config;
  },
  error => {
    return Promise.reject(error);
  }
);
