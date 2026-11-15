FROM node:22-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=${BACKEND_URL}
ENV NODE_ENV=production

RUN npm run build && chown -R node:node /app

USER node
EXPOSE 3000

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0"]
