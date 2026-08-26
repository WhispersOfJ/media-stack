# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| latest  | ✅ Active development |
| < latest | ❌ No support     |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

### How to Report

1. **Email:** Open a [GitHub Security Advisory](https://github.com/WhispersOfJ/media-stack/security/advisories/new)
2. **Include:**
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### What to Expect

- **Acknowledgment:** Within 48 hours
- **Assessment:** Within 1 week
- **Fix timeline:** Depends on severity
  - Critical: 24-48 hours
  - High: 1 week
  - Medium/Low: Next release

## Security Best Practices

### Deployment

- **Never expose services directly to the internet** without a reverse proxy
- **Use strong, unique API keys** for all services (Radarr, Sonarr, Prowlarr, NzbDAV)
- **Enable HTTPS** via Caddy/Nginx reverse proxy
- **Restrict network access** to trusted IPs only
- **Keep containers updated** — enable Watchtower for automatic updates

### API Keys

- Store API keys in `.env` file (never commit to git)
- Use Docker secrets for production deployments
- Rotate keys periodically
- Use least-privilege access where possible

### Container Security

- Run containers as non-root when possible
- Use read-only filesystem mounts for config
- Limit container resources (CPU/memory)
- Use `no-new-privileges` security option

### Network

- Isolate services on internal Docker network
- Only expose necessary ports
- Use firewall rules to restrict access
- Monitor logs for suspicious activity

## Known Security Considerations

### This Stack

- **Control Panel** exposes host operations — protect with authentication
- **NzbDAV** handles Usenet credentials — encrypt at rest
- **Metacache** proxies API calls — rate-limit external requests
- **Landing page** is public — no sensitive data exposed

### Dependencies

- Monitor Dependabot alerts for vulnerable packages
- Review Trivy scan results for container image CVEs
- Update base images regularly

## Compliance

This project is for personal/home use and does not require formal compliance certifications. However, we follow security best practices to protect user data and infrastructure.

## Contact

For security inquiries, use [GitHub Security Advisories](https://github.com/WhispersOfJ/media-stack/security/advisories/new).
