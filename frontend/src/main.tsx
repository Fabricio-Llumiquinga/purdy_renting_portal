import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { configureAmplify } from './config/aws-config.ts'
import { SKIP_AUTH } from './config/demo.ts'
import './index.css'

// En modo demo NO configuramos Amplify (los valores de Cognito son placeholders
// y provocarian errores). En produccion se configura normalmente.
if (!SKIP_AUTH) {
  configureAmplify()
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)