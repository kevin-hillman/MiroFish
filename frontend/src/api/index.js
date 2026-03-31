import axios from 'axios'
import { useAuth } from '../auth/supabase'

// Axios-Instanz erstellen
const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 300000, // 5 Minuten Timeout (Ontologie-Generierung kann laenger dauern)
  headers: {
    'Content-Type': 'application/json'
  }
})

// Anfrage-Interceptor
service.interceptors.request.use(
  config => {
    const { getToken } = useAuth()
    const token = getToken()
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  },
  error => {
    console.error('Request error:', error)
    return Promise.reject(error)
  }
)

// Antwort-Interceptor (Fehlertoleranz-Wiederholungsmechanismus)
service.interceptors.response.use(
  response => {
    const res = response.data
    
    // Wenn der zurueckgegebene Statuscode nicht 'success' ist, Fehler ausloesen
    if (!res.success && res.success !== undefined) {
      console.error('API Error:', res.error || res.message || 'Unknown error')
      return Promise.reject(new Error(res.error || res.message || 'Error'))
    }
    
    return res
  },
  error => {
    console.error('Response error:', error)
    
    // Timeout behandeln
    if (error.code === 'ECONNABORTED' && error.message.includes('timeout')) {
      console.error('Request timeout')
    }
    
    // Netzwerkfehler behandeln
    if (error.message === 'Network Error') {
      console.error('Network error - please check your connection')
    }
    
    return Promise.reject(error)
  }
)

// Anfragefunktion mit Wiederholungslogik
export const requestWithRetry = async (requestFn, maxRetries = 3, delay = 1000) => {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await requestFn()
    } catch (error) {
      if (i === maxRetries - 1) throw error
      
      console.warn(`Request failed, retrying (${i + 1}/${maxRetries})...`)
      await new Promise(resolve => setTimeout(resolve, delay * Math.pow(2, i)))
    }
  }
}

export default service
