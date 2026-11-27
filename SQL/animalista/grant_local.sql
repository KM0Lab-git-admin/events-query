-- Solo para el MySQL de docker-compose: el usuario de aplicación de events_db
-- (events_user) también accede a animalista_db. No ejecutar en Railway.
GRANT ALL PRIVILEGES ON `animalista_db`.* TO 'events_user'@'%';
FLUSH PRIVILEGES;
