import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { initAuth } from './auth/supabase'

const app = createApp(App)

app.use(router)

initAuth().then(() => {
  app.mount('#app')
})
