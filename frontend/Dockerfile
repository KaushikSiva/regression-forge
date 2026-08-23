FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
ARG VITE_API_URL=http://localhost:4400
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.27-alpine
ENV API_SCHEME=http
ENV API_HOST=regressionforge-api
ENV API_PORT=8000
ENV NGINX_ENVSUBST_FILTER=^(API_SCHEME|API_HOST|API_PORT)$
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
