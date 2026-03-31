<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-brand">MIROFISH</div>
      <div class="login-subtitle">Anmeldung erforderlich</div>

      <form class="login-form" @submit.prevent="handleLogin">
        <div class="input-group">
          <label class="input-label" for="email">E-Mail</label>
          <input
            id="email"
            v-model="email"
            type="email"
            class="login-input"
            placeholder="name@beispiel.de"
            required
            :disabled="submitting"
          />
        </div>

        <div class="input-group">
          <label class="input-label" for="password">Passwort</label>
          <input
            id="password"
            v-model="password"
            type="password"
            class="login-input"
            placeholder="Passwort eingeben"
            :disabled="submitting"
          />
        </div>

        <div v-if="errorMsg" class="error-message">{{ errorMsg }}</div>
        <div v-if="infoMsg" class="info-message">{{ infoMsg }}</div>

        <button
          type="submit"
          class="login-btn"
          :disabled="submitting || !email"
        >
          <span v-if="!submitting">Anmelden</span>
          <span v-else>Wird geladen...</span>
        </button>

        <button
          type="button"
          class="magic-link-btn"
          :disabled="submitting || !email"
          @click="handleMagicLink"
        >
          Magic Link senden
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../auth/supabase'

const router = useRouter()
const { signInWithEmail, signInWithMagicLink } = useAuth()

const email = ref('')
const password = ref('')
const errorMsg = ref('')
const infoMsg = ref('')
const submitting = ref(false)

async function handleLogin() {
  if (!email.value) return
  errorMsg.value = ''
  infoMsg.value = ''
  submitting.value = true

  try {
    await signInWithEmail(email.value, password.value)
    router.push('/')
  } catch (e) {
    errorMsg.value = e.message || 'Anmeldung fehlgeschlagen'
  } finally {
    submitting.value = false
  }
}

async function handleMagicLink() {
  if (!email.value) return
  errorMsg.value = ''
  infoMsg.value = ''
  submitting.value = true

  try {
    await signInWithMagicLink(email.value)
    infoMsg.value = 'Magic Link wurde gesendet. Bitte pruefen Sie Ihr Postfach.'
  } catch (e) {
    errorMsg.value = e.message || 'Magic Link konnte nicht gesendet werden'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  background: var(--white, #FFFFFF);
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-sans, 'Space Grotesk', system-ui, sans-serif);
}

.login-card {
  width: 100%;
  max-width: 400px;
  padding: 50px 40px;
  border: 1px solid #E5E5E5;
}

.login-brand {
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  font-weight: 800;
  font-size: 1.6rem;
  letter-spacing: 1px;
  color: var(--black, #000000);
  margin-bottom: 8px;
}

.login-subtitle {
  font-size: 0.9rem;
  color: #999;
  margin-bottom: 40px;
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.input-label {
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  font-size: 0.75rem;
  color: #666;
  letter-spacing: 0.5px;
}

.login-input {
  width: 100%;
  padding: 14px 16px;
  border: 1px solid #DDD;
  background: #FAFAFA;
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  font-size: 0.9rem;
  outline: none;
  transition: border-color 0.2s;
  box-sizing: border-box;
}

.login-input:focus {
  border-color: var(--black, #000000);
}

.login-input:disabled {
  opacity: 0.5;
}

.error-message {
  background: #FFF0F0;
  border-left: 3px solid var(--orange, #FF4500);
  padding: 10px 14px;
  font-size: 0.85rem;
  color: #CC0000;
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
}

.info-message {
  background: #F0FFF0;
  border-left: 3px solid #22AA22;
  padding: 10px 14px;
  font-size: 0.85rem;
  color: #227722;
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
}

.login-btn {
  width: 100%;
  padding: 16px;
  background: var(--black, #000000);
  color: var(--white, #FFFFFF);
  border: 1px solid var(--black, #000000);
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  font-weight: 700;
  font-size: 1rem;
  cursor: pointer;
  letter-spacing: 1px;
  transition: all 0.2s;
}

.login-btn:hover:not(:disabled) {
  background: var(--orange, #FF4500);
  border-color: var(--orange, #FF4500);
}

.login-btn:disabled {
  background: #E5E5E5;
  border-color: #E5E5E5;
  color: #999;
  cursor: not-allowed;
}

.magic-link-btn {
  width: 100%;
  padding: 14px;
  background: transparent;
  color: var(--black, #000000);
  border: 1px solid #DDD;
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  font-weight: 500;
  font-size: 0.9rem;
  cursor: pointer;
  letter-spacing: 0.5px;
  transition: all 0.2s;
}

.magic-link-btn:hover:not(:disabled) {
  border-color: var(--black, #000000);
}

.magic-link-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
