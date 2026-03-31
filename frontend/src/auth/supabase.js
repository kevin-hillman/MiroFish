import { createClient } from '@supabase/supabase-js'
import { ref, computed } from 'vue'

let supabase = null
const user = ref(null)
const session = ref(null)
const authEnabled = ref(false)
const loading = ref(true)

export async function initAuth() {
  try {
    const res = await fetch('/api/auth/status')
    const data = await res.json()
    authEnabled.value = data.auth_enabled

    if (!data.auth_enabled) {
      loading.value = false
      return
    }

    supabase = createClient(data.supabase_url, data.supabase_anon_key)

    const { data: { session: currentSession } } = await supabase.auth.getSession()
    if (currentSession) {
      session.value = currentSession
      user.value = currentSession.user
    }

    supabase.auth.onAuthStateChange((_event, newSession) => {
      session.value = newSession
      user.value = newSession?.user || null
    })
  } catch (e) {
    console.warn('Auth init failed:', e)
    authEnabled.value = false
  } finally {
    loading.value = false
  }
}

export function useAuth() {
  const isAuthenticated = computed(() => !authEnabled.value || !!session.value)
  const getToken = () => session.value?.access_token || null

  async function signInWithEmail(email, password) {
    if (!supabase) throw new Error('Auth nicht konfiguriert')
    const { data, error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) throw error
    return data
  }

  async function signInWithMagicLink(email) {
    if (!supabase) throw new Error('Auth nicht konfiguriert')
    const { data, error } = await supabase.auth.signInWithOtp({ email })
    if (error) throw error
    return data
  }

  async function signOut() {
    if (!supabase) return
    await supabase.auth.signOut()
    user.value = null
    session.value = null
  }

  return {
    user,
    session,
    authEnabled,
    loading,
    isAuthenticated,
    getToken,
    signInWithEmail,
    signInWithMagicLink,
    signOut
  }
}
