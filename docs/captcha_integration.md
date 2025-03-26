# CAPTCHA Integration Guide

This document explains how to integrate Google reCAPTCHA v2 with the Speech Assistant API's authentication system.

## Backend Configuration

The backend is already configured to validate reCAPTCHA responses on the `/auth/register` and `/auth/login` endpoints. The backend expects a form field named `captcha_response` containing the reCAPTCHA token from the frontend.

## Environment Variables

The following environment variables need to be set for CAPTCHA to work:

```
RECAPTCHA_SITE_KEY=your-site-key  # Used in frontend
RECAPTCHA_SECRET_KEY=your-secret-key  # Used in backend
```

You can obtain these keys by registering your site at [Google reCAPTCHA Admin Console](https://www.google.com/recaptcha/admin).

## Frontend Integration

### 1. Add the reCAPTCHA Script to Your HTML

Add the following script tag to your HTML document:

```html
<script src="https://www.google.com/recaptcha/api.js" async defer></script>
```

### 2. Retrieve the Site Key

The frontend can get the reCAPTCHA site key through the API:

```javascript
// Fetch the site key
async function getCaptchaKey() {
  const response = await fetch("/auth/captcha-key");
  const data = await response.json();
  return data.site_key;
}
```

### 3. Add the reCAPTCHA Widget to Your Forms

Add the reCAPTCHA widget to your login and registration forms:

```html
<form id="login-form">
  <input type="email" name="email" placeholder="Email" required />
  <input type="password" name="password" placeholder="Password" required />

  <!-- Add reCAPTCHA widget -->
  <div class="g-recaptcha" data-sitekey="YOUR_SITE_KEY"></div>

  <button type="submit">Login</button>
</form>
```

Replace `YOUR_SITE_KEY` with the actual site key.

### 4. Handle Form Submission

When submitting the form, include the reCAPTCHA response:

```javascript
async function handleSubmit(event) {
  event.preventDefault();

  // Get reCAPTCHA response
  const captchaResponse = grecaptcha.getResponse();

  // Create form data
  const formData = new FormData();
  formData.append("username", document.querySelector('[name="email"]').value);
  formData.append(
    "password",
    document.querySelector('[name="password"]').value
  );
  formData.append("captcha_response", captchaResponse);

  // Send request
  try {
    const response = await fetch("/auth/login", {
      method: "POST",
      body: formData,
    });

    if (response.ok) {
      const data = await response.json();
      // Handle successful login
      localStorage.setItem("access_token", data.access_token);
      window.location.href = "/dashboard";
    } else {
      // Handle errors
      const error = await response.json();
      showError(error.detail);
      // Reset reCAPTCHA
      grecaptcha.reset();
    }
  } catch (error) {
    console.error("Login error:", error);
    showError("An error occurred during login.");
    // Reset reCAPTCHA
    grecaptcha.reset();
  }
}

// Attach event listener to form
document.getElementById("login-form").addEventListener("submit", handleSubmit);
```

## Example React Component

Here's an example of a React component implementing reCAPTCHA:

```jsx
import React, { useState, useEffect } from "react";
import axios from "axios";

function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [siteKey, setSiteKey] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    // Load reCAPTCHA script
    const script = document.createElement("script");
    script.src = "https://www.google.com/recaptcha/api.js";
    script.async = true;
    script.defer = true;
    document.body.appendChild(script);

    // Get site key
    async function fetchSiteKey() {
      try {
        const response = await axios.get("/auth/captcha-key");
        setSiteKey(response.data.site_key);
      } catch (error) {
        console.error("Failed to fetch CAPTCHA site key:", error);
      }
    }

    fetchSiteKey();

    return () => {
      document.body.removeChild(script);
    };
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    // Get reCAPTCHA response
    const captchaResponse = window.grecaptcha.getResponse();

    // Create form data
    const formData = new FormData();
    formData.append("username", email);
    formData.append("password", password);
    formData.append("captcha_response", captchaResponse);

    try {
      const response = await axios.post("/auth/login", formData);
      // Handle successful login
      localStorage.setItem("access_token", response.data.access_token);
      window.location.href = "/dashboard";
    } catch (error) {
      setError(error.response?.data?.detail || "An error occurred");
      // Reset reCAPTCHA
      window.grecaptcha.reset();
    }
  };

  return (
    <div className="login-form">
      <h2>Login</h2>
      {error && <div className="error">{error}</div>}
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div className="form-group">
          <label>Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        {siteKey && <div className="g-recaptcha" data-sitekey={siteKey}></div>}
        <button type="submit">Login</button>
      </form>
    </div>
  );
}

export default LoginForm;
```

## Testing CAPTCHA

For development and testing purposes, you can set `RECAPTCHA_SECRET_KEY=` (empty) in your `.env` file, which will cause the backend to skip CAPTCHA validation.

For production, you must set valid reCAPTCHA keys.

## Troubleshooting

### 1. CAPTCHA Not Loading

Make sure:

- The reCAPTCHA script is loaded correctly
- Your site key is valid
- The domain is allowed in the reCAPTCHA admin console

### 2. CAPTCHA Validation Failing

Check:

- That the `captcha_response` field is being sent correctly
- Your secret key is valid
- The domain matches what's configured in the reCAPTCHA admin console

### 3. Network Issues

If your application is behind a proxy or firewall, ensure that requests to Google's reCAPTCHA verification endpoint are allowed.
