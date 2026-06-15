import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './locales/en.json'
import ru from './locales/ru.json'

const stored = localStorage.getItem('lang')
const initial = stored === 'en' || stored === 'ru' ? stored : 'ru'

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    ru: { translation: ru },
  },
  lng: initial, // default to Russian when nothing is stored
  fallbackLng: 'en',
  supportedLngs: ['ru', 'en'],
  interpolation: { escapeValue: false },
})

export default i18n
