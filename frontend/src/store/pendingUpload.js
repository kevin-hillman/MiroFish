/**
 * Temporaere Speicherung von Dateien und Anforderungen fuer den Upload
 * Wird verwendet, um nach dem Klick auf "Engine starten" auf der Startseite sofort weiterzuleiten und den API-Aufruf erst auf der Prozessseite durchzufuehren
 */
import { reactive } from 'vue'

const state = reactive({
  files: [],
  simulationRequirement: '',
  isPending: false
})

export function setPendingUpload(files, requirement) {
  state.files = files
  state.simulationRequirement = requirement
  state.isPending = true
}

export function getPendingUpload() {
  return {
    files: state.files,
    simulationRequirement: state.simulationRequirement,
    isPending: state.isPending
  }
}

export function clearPendingUpload() {
  state.files = []
  state.simulationRequirement = ''
  state.isPending = false
}

export default state
