FROM node:16
ARG IMAGE_TAG
WORKDIR /app
RUN npm install -g @vue/cli
RUN npm config set registry https://registry.npmmirror.com
COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
#RUN echo "y" | vue create log-analyze --default --packageManager=npm --no-git
#WORKDIR /app/log-analyze
#RUN npm install
EXPOSE 8080

#CMD ["npm", "run", "serve"]
ENTRYPOINT ["/entrypoint.sh"]
