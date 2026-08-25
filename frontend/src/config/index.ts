//@ts-nocheck
import axios from 'axios';

// Security: Enforce HTTPS for API communication in production to prevent
// credential and token interception. The PLACE_HOLDER will be replaced
// during deployment with the actual API URL.
const FLASK_API_URL = "PLACE_HOLDER";

// Validate that the API URL uses HTTPS in production environments
const validateApiUrl = (url: string): void => {
  // Allow localhost and 127.0.0.1 for development
  const isLocalhost = url.includes('localhost') || url.includes('127.0.0.1');
  
  // In production (non-localhost), enforce HTTPS
  if (!isLocalhost && !url.startsWith('https://')) {
    console.error(
      'Security Error: API URL must use HTTPS in production. ' +
      'Current URL: ' + url + '. ' +
      'Plaintext HTTP exposes credentials and authentication tokens to interception.'
    );
    // In strict production mode, throw an error to prevent insecure connections
    if (process.env.NODE_ENV === 'production') {
      throw new Error('HTTPS is required for API communication in production');
    }
  }
};

// Validate the API URL before creating the axios instance
if (FLASK_API_URL !== "PLACE_HOLDER") {
  validateApiUrl(FLASK_API_URL);
}

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
