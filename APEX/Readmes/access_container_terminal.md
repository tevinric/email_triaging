# To access the container terminal follow theses steps:

1. Create the docker container image in cmd:

```docker build -t <container-name> .```

2. Run the container in terminal so that it will appear in Rancher Desktop: 

```docker run -d <container-name>```

NB: the "-d" will run the container image in the background

3. Now that the container image is running, you can access the CMD terminal again by CNTRL+C

4. Now run the command below to get the process ID  of your running docker container image:

```docker ps```

5. Get the process ID for your container image and copy it and paste it in the terminal to get the container terminal.

6. Now run the following command to log into the terminal of your container image:

```docker exec -it <conatiner-id/name> /bin/bash```

7. You are now in the terminal of your docker container.


## TIP 

### How to view the ODBC Drivers available in your linux environment

```cat /etc/odbcinst.ini```