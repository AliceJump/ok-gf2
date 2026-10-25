import React from 'react';
import ReactDOM from 'react-dom/client';
import * as TooltipPrimitive from '@radix-ui/react-tooltip';
import { Toaster } from 'sonner';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <TooltipPrimitive.Provider delayDuration={300}>
      <App />
      <Toaster
        position="bottom-right"
        richColors
        closeButton
        toastOptions={{
          style: {
            background: 'var(--color-bg-secondary)',
            color: 'var(--color-text-primary)',
            border: '1px solid var(--color-border)',
          },
        }}
      />
    </TooltipPrimitive.Provider>
  </React.StrictMode>,
);
