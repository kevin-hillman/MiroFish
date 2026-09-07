import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import Step4Report from '../src/components/Step4Report.vue'
import { getAgentLog, getConsoleLog, getReport } from '../src/api/report'

vi.mock('../src/api/report', () => ({
  getReport: vi.fn(),
  getAgentLog: vi.fn(),
  getConsoleLog: vi.fn()
}))

const savedReport = (overrides = {}) => ({
  report_id: 'report_saved',
  simulation_id: 'sim_saved',
  status: 'completed',
  error: null,
  outline: {
    title: 'Buybacklinks-Auswertung',
    summary: 'Auswertung der Originalaktionen, keine Marktforschung.',
    sections: [
      { title: 'Beobachtungen', content: '**Herkunft:** Codex-Auswertung, kein nativer ReportAgent-Lauf.' },
      { title: 'Kaufblocker', content: 'Aktuelle Angebotsdaten fehlen.' },
      { title: 'Grenzen', content: 'Sechs KI-Rollen sind keine sechs Kunden.' }
    ]
  },
  ...overrides
})

const reportWithSectionContent = (content) => ({
  report_id: 'report_table_fixture',
  simulation_id: 'sim_table_fixture',
  status: 'completed',
  error: null,
  outline: {
    title: 'Synthetic report',
    summary: 'Generic renderer fixture.',
    sections: [{ title: 'Table section', content }]
  }
})

const logResponse = (logs = [], fromLine = 0) => ({
  success: true,
  data: { logs, from_line: fromLine, total_lines: fromLine + logs.length, has_more: false }
})

const event = (action, details = {}, sectionIndex = null) => ({
  action, details, section_index: sectionIndex,
  section_title: sectionIndex ? 'Beobachtungen' : null,
  timestamp: `2026-09-07T12:00:0${sectionIndex || 0}`,
  elapsed_seconds: 0
})

let wrapper

async function openReport(reportId = 'report_saved') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }]
  })
  await router.push('/')
  wrapper = mount(Step4Report, {
    props: { reportId, simulationId: 'sim_saved', systemLogs: [] },
    global: { plugins: [router] }
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.useFakeTimers()
  getReport.mockResolvedValue({ success: true, data: savedReport() })
  getAgentLog.mockImplementation((_, fromLine = 0) => Promise.resolve(logResponse(
    fromLine === 0 ? [event('codex_evidence_report_saved', { author: 'Codex' })] : [],
    fromLine
  )))
  getConsoleLog.mockResolvedValue(logResponse())
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  vi.useRealTimers()
  vi.resetAllMocks()
})

describe('gespeicherte Reports', () => {
  it('zeigt den fertigen Bericht ohne native Kapitel- oder Abschlussereignisse', async () => {
    await openReport()
    expect(wrapper.find('h1').exists()).toBe(true)
    expect(wrapper.find('h1').text()).toBe('Buybacklinks-Auswertung')
    expect(wrapper.findAll('.generated-content')).toHaveLength(3)
    expect(wrapper.text()).toContain('Codex-Auswertung, kein nativer ReportAgent-Lauf.')
    expect(wrapper.text()).toContain('Sechs KI-Rollen sind keine sechs Kunden.')
    expect(wrapper.find('.metric-value').text()).toBe('3/3')
    expect(wrapper.find('.waiting-placeholder').exists()).toBe(false)
    expect(wrapper.emitted('update-status').at(-1)).toEqual(['completed'])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('laesst historische Protokolltexte den gespeicherten Bericht nicht ueberschreiben', async () => {
    getAgentLog.mockResolvedValue(logResponse([
      event('planning_complete', { outline: savedReport().outline }),
      event('section_complete', { content: 'VERALTETER ENTWURF' }, 1),
      event('report_complete')
    ]))
    await openReport()
    expect(wrapper.findAll('.generated-content')[0].text()).toContain('Codex-Auswertung')
    expect(wrapper.findAll('.generated-content')[0].text()).not.toContain('VERALTETER ENTWURF')
    expect(wrapper.find('.metric-value').text()).toBe('3/3')
  })

  it('zeigt fertigen Inhalt auch bei einem nicht verfuegbaren Diagnoseprotokoll', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    getAgentLog.mockRejectedValue(new Error('Protokoll nicht verfuegbar'))
    getConsoleLog.mockRejectedValue(new Error('Protokoll nicht verfuegbar'))
    await openReport()
    expect(wrapper.findAll('.generated-content')).toHaveLength(3)
    expect(wrapper.emitted('update-status').at(-1)).toEqual(['completed'])
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe('laufende und fehlgeschlagene Reports', () => {
  it.each([404, 500])('uebersteht einen voruebergehenden HTTP-%i-Fehler beim Speichern', async (status) => {
    getReport.mockRejectedValueOnce(Object.assign(new Error('Bericht voruebergehend nicht lesbar'), {
      response: { status }
    }))
    await openReport()
    expect(wrapper.find('[role="alert"]').text()).toContain('Automatischer neuer Versuch')
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(wrapper.findAll('.generated-content')).toHaveLength(3)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.emitted('update-status').at(-1)).toEqual(['completed'])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('begrenzt die automatischen Wiederholungen bei einem dauerhaft fehlenden Bericht', async () => {
    getReport.mockRejectedValue(Object.assign(new Error('Bericht nicht gefunden'), { response: { status: 404 } }))
    await openReport()
    await vi.advanceTimersByTimeAsync(10000)
    await flushPromises()
    expect(getReport).toHaveBeenCalledTimes(3)
    expect(wrapper.find('[role="alert"]').text()).toContain('Bericht nicht gefunden')
    expect(wrapper.find('[role="alert"]').text()).not.toContain('Automatischer neuer Versuch')
    expect(wrapper.emitted('update-status').at(-1)).toEqual(['error'])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('wartet nach dem Abschlussereignis noch auf den tatsaechlich gespeicherten Report', async () => {
    getReport.mockResolvedValueOnce({ success: true, data: savedReport({ status: 'generating' }) })
    getAgentLog.mockResolvedValue(logResponse([event('report_complete')]))
    await openReport()
    expect(wrapper.emitted('update-status').at(-1)).toEqual(['processing'])
    expect(vi.getTimerCount()).toBe(1)
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(wrapper.findAll('.generated-content')).toHaveLength(3)
    expect(wrapper.emitted('update-status').at(-1)).toEqual(['completed'])
  })

  it('zeigt Kapitel waehrend des Laufs und erkennt den gespeicherten Abschluss ohne Schlussereignis', async () => {
    getReport.mockResolvedValueOnce({ success: true, data: savedReport({ status: 'generating' }) })
    getAgentLog.mockImplementation((_, fromLine = 0) => Promise.resolve(logResponse(
      fromLine === 0 ? [
        event('planning_complete', { outline: savedReport().outline }),
        event('section_complete', { content: 'Laufender erster Abschnitt' }, 1)
      ] : [], fromLine
    )))
    await openReport()
    expect(wrapper.find('.metric-value').text()).toBe('1/3')
    expect(wrapper.text()).toContain('Laufender erster Abschnitt')
    expect(wrapper.emitted('update-status')?.at(-1)).not.toEqual(['completed'])
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(wrapper.find('.metric-value').text()).toBe('3/3')
    expect(wrapper.emitted('update-status').at(-1)).toEqual(['completed'])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('zeigt einen gespeicherten Fehler statt endloser Generierung', async () => {
    getReport.mockResolvedValue({ success: true, data: savedReport({ status: 'failed', error: 'Generierung fehlgeschlagen', outline: null }) })
    await openReport()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.find('[role="alert"]').text()).toContain('Generierung fehlgeschlagen')
    expect(wrapper.emitted('update-status').at(-1)).toEqual(['error'])
    expect(wrapper.find('.waiting-placeholder').exists()).toBe(false)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('meldet einen nicht ladbaren Bericht sichtbar und beendet die Abfragen', async () => {
    getReport.mockRejectedValue(new Error('Bericht nicht gefunden'))
    await openReport()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.find('[role="alert"]').text()).toContain('Bericht nicht gefunden')
    expect(wrapper.emitted('update-status').at(-1)).toEqual(['error'])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('startet bei langsamen Antworten keine ueberlappenden Statusabfragen', async () => {
    let resolveRequest
    getReport.mockReturnValue(new Promise(resolve => { resolveRequest = resolve }))
    await openReport()
    await vi.advanceTimersByTimeAsync(6000)
    expect(getReport).toHaveBeenCalledTimes(1)
    resolveRequest({ success: true, data: savedReport() })
    await flushPromises()
    expect(wrapper.find('.metric-value').text()).toBe('3/3')
  })

  it('ignoriert eine alte Antwort nach Wechsel zu einer anderen Report-ID', async () => {
    let resolveOld
    getReport.mockImplementation(reportId => reportId === 'report_old'
      ? new Promise(resolve => { resolveOld = resolve })
      : Promise.resolve({ success: true, data: savedReport() }))
    await openReport('report_old')
    await wrapper.setProps({ reportId: 'report_saved' })
    await flushPromises()
    expect(wrapper.find('h1').exists()).toBe(true)
    expect(wrapper.find('h1').text()).toBe('Buybacklinks-Auswertung')
    resolveOld({ success: true, data: savedReport({ report_id: 'report_old', outline: { title: 'Alter Report', summary: '', sections: [] } }) })
    await flushPromises()
    expect(wrapper.find('h1').text()).toBe('Buybacklinks-Auswertung')
    expect(wrapper.findAll('.generated-content')).toHaveLength(3)
  })
})

describe('Markdown-Tabellen im gespeicherten Report', () => {
  it('rendert einen Vier-Spalten-Header mit sechs Datenzeilen semantisch', async () => {
    const table = [
      '| Segment | Score | Region | Status |',
      '| --- | --- | --- | --- |',
      '| Buyer 01 | 10 | Zone A | Ready |',
      '| Buyer 02 | 20 | Zone B | Ready |',
      '| Buyer 03 | 30 | Zone C | Ready |',
      '| Buyer 04 | 40 | Zone D | Ready |',
      '| Buyer 05 | 50 | Zone E | Ready |',
      '| Buyer 06 | 60 | Zone F | Ready |'
    ].join('\n')
    getReport.mockResolvedValue({ success: true, data: reportWithSectionContent(table) })

    await openReport('report_table_fixture')

    const generated = wrapper.find('.generated-content')
    const renderedTable = generated.find('table')
    expect(renderedTable.exists()).toBe(true)
    expect(renderedTable.findAll('thead tr')).toHaveLength(1)
    expect(renderedTable.findAll('thead th')).toHaveLength(4)
    renderedTable.findAll('thead th').forEach(header => {
      expect(header.attributes('scope')).toBe('col')
    })
    expect(renderedTable.findAll('tbody tr')).toHaveLength(6)
    expect(renderedTable.findAll('tbody td')).toHaveLength(24)
  })

  it('bewahrt Inlineformatierung und behandelt Escaped- und Code-Pipes als Zelltext', async () => {
    const table = [
      '| Name | Description | Snippet | Outcome |',
      '| :--- | :---: | ---: | --- |',
      '| **Bold** | _Italic_ | `x|y` | left \\| right |'
    ].join('\n')
    getReport.mockResolvedValue({ success: true, data: reportWithSectionContent(table) })

    await openReport('report_table_fixture')

    const cells = wrapper.findAll('.generated-content tbody td')
    expect(cells).toHaveLength(4)
    expect(cells[0].find('strong').text()).toBe('Bold')
    expect(cells[1].find('em').text()).toBe('Italic')
    expect(cells[2].find('code').text()).toBe('x|y')
    expect(cells[3].text()).toBe('left | right')
  })

  it('haelt Tabelle, Absaetze und Liste als getrennte Blockelemente', async () => {
    const content = [
      'Before paragraph.',
      '',
      '| Name | Score | Region | Status |',
      '| --- | --- | --- | --- |',
      '| Buyer 01 | 10 | Zone A | Ready |',
      '',
      'After paragraph.',
      '',
      '- First item',
      '- Second item'
    ].join('\n')
    getReport.mockResolvedValue({ success: true, data: reportWithSectionContent(content) })

    await openReport('report_table_fixture')

    const generated = wrapper.find('.generated-content').element
    const children = Array.from(generated.children)
    expect(children.map(child => child.tagName)).toEqual(['P', 'DIV', 'P', 'UL'])
    expect(children[0].textContent).toBe('Before paragraph.')
    expect(children[1].classList.contains('md-table-wrapper')).toBe(true)
    expect(children[1].querySelector('table')).not.toBeNull()
    expect(children[2].textContent).toBe('After paragraph.')
    expect(generated.querySelector('p > table')).toBeNull()
    expect(generated.querySelector('p > .md-table-wrapper')).toBeNull()
    expect(generated.querySelector('br + .md-table-wrapper')).toBeNull()
    expect(generated.querySelector('.md-table-wrapper + br')).toBeNull()
    expect(children[3].querySelectorAll('li')).toHaveLength(2)
  })

  it('laesst eine tabellenaehnliche Struktur innerhalb eines Fenced Code Blocks als Code', async () => {
    const code = [
      '```text',
      '| Name | Score |',
      '| --- | --- |',
      '| Buyer 01 | 10 |',
      '```'
    ].join('\n')
    getReport.mockResolvedValue({ success: true, data: reportWithSectionContent(code) })

    await openReport('report_table_fixture')

    const generated = wrapper.find('.generated-content')
    expect(generated.find('table').exists()).toBe(false)
    expect(generated.find('pre.code-block').exists()).toBe(true)
    expect(generated.find('pre.code-block code').text()).toContain('| Name | Score |')
  })

  it('escaped HTML in Tabellenzellen bleibt inert und wird als Text angezeigt', async () => {
    const table = [
      '| Name | Image markup | Script markup | Status |',
      '| --- | --- | --- | --- |',
      '| Buyer 01 | <img src="x" onerror="alert(1)"> | <script>alert(1)</script> | Ready |'
    ].join('\n')
    getReport.mockResolvedValue({ success: true, data: reportWithSectionContent(table) })

    await openReport('report_table_fixture')

    const cells = wrapper.findAll('.generated-content tbody td')
    expect(cells).toHaveLength(4)
    expect(cells[1].text()).toBe('<img src="x" onerror="alert(1)">')
    expect(cells[2].text()).toBe('<script>alert(1)</script>')
    expect(wrapper.find('.generated-content img').exists()).toBe(false)
    expect(wrapper.find('.generated-content script').exists()).toBe(false)
    expect(wrapper.find('.generated-content [onerror]').exists()).toBe(false)
  })

  it('erzeugt bei einem finalen Newline keinen leeren Absatz hinter der Tabelle', async () => {
    const table = '| A | B |\n| --- | --- |\n| 1 | 2 |\n'
    getReport.mockResolvedValue({ success: true, data: reportWithSectionContent(table) })

    await openReport('report_table_fixture')

    const generated = wrapper.find('.generated-content').element
    expect(Array.from(generated.children).map(child => child.tagName)).toEqual(['DIV'])
    expect(generated.querySelector('.md-table-wrapper + p')).toBeNull()
  })

  it.each([
    ['vier Leerzeichen', '    '],
    ['einen Tab', '\t']
  ])('behandelt %s vor allen Tabellenzeilen weiterhin als Rohtext', async (_, indent) => {
    const content = [
      `${indent}| A | B |`,
      `${indent}| --- | --- |`,
      `${indent}| 1 | 2 |`
    ].join('\n')
    getReport.mockResolvedValue({ success: true, data: reportWithSectionContent(content) })

    await openReport('report_table_fixture')

    const generated = wrapper.find('.generated-content')
    expect(generated.find('table').exists()).toBe(false)
    expect(generated.text()).toContain('| A | B |')
    expect(generated.text()).toContain('| --- | --- |')
    expect(generated.text()).toContain('| 1 | 2 |')
  })

  it('bewahrt den bisherigen Abstand nach einem Fenced Code Block', async () => {
    const content = '```js\ncode\n```\nAfter'
    getReport.mockResolvedValue({ success: true, data: reportWithSectionContent(content) })

    await openReport('report_table_fixture')

    expect(wrapper.find('.generated-content').html()).toContain('</pre><br>After')
  })

  it('bewahrt wörtliche Unterstriche und Sternchen in Tabellen-Inline-Code', async () => {
    const table = [
      '| A | B |',
      '| --- | --- |',
      '| `a_b_c` | `*literal*` |'
    ].join('\n')
    getReport.mockResolvedValue({ success: true, data: reportWithSectionContent(table) })

    await openReport('report_table_fixture')

    const cells = wrapper.findAll('.generated-content tbody td')
    expect(cells).toHaveLength(2)
    expect(cells[0].find('code').text()).toBe('a_b_c')
    expect(cells[0].find('code em').exists()).toBe(false)
    expect(cells[1].find('code').text()).toBe('*literal*')
    expect(cells[1].find('code em').exists()).toBe(false)
  })
})
