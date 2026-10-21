# Statischer Export: mit Node bauen, mit nginx ausliefern (Alternative zu Cloudflare, z. B. für docker compose)
FROM node:20-slim AS build
WORKDIR /app
COPY web/package.json web/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY web .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_API_KEY=demo-schluessel
ARG NEXT_PUBLIC_SUPABASE_URL=
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL NEXT_PUBLIC_API_KEY=$NEXT_PUBLIC_API_KEY \
    NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/out /usr/share/nginx/html
RUN printf 'server {\n  listen 3000;\n  root /usr/share/nginx/html;\n  location / { try_files $uri $uri.html $uri/ =404; }\n  error_page 404 /404.html;\n}\n' > /etc/nginx/conf.d/default.conf
EXPOSE 3000
