# Project: APEX AI Portfolio Management System
# Course: Graduation Project / Engineering Project
# Team Members:
# - Saleem A. S. AbuZaid
# - Rashad Naghdiyev
# Advisor:
# Prof.Dr. Selim Akyokuş
# Description:
# - Container and deployment configuration for the APEX AI project environment.
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install --legacy-peer-deps
COPY . .
EXPOSE 3000
CMD ["npm", "start"]
