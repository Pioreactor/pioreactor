# Dockerfile for Pioreactor React frontend
FROM node:20-alpine

# set working directory
WORKDIR /app/frontend

# install dependencies
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# copy source code
COPY frontend/ ./

# expose development port
EXPOSE 3000

# start React development server
CMD ["npm", "start"]
