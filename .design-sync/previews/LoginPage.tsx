import * as React from 'react';
import { LoginPage } from 'verifarms-frontend';

// Full-screen auth screen — rendered as a single card (see cfg.overrides.LoginPage).
export const SignIn = () => <LoginPage onLogin={() => {}} />;
