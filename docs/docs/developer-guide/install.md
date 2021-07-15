# Install the App

Whether you plan to run with docker-copmose or locally, you will need to install
the app to a repository to get the full functionality.
So the next step is to install your app, ideally to your fork of spack. To do this,
go back to the App in developer settings and click on it's public url, which
will look something like `https://github.com/apps/<appname>`. You can then click
to install the app to your fork of spack. Then make sure your app is running,
and open a pull request. If you watch the server logs you should see:

```console
$ docker-compose logs -f
spackbot_1  | INFO:aiohttp.access:172.19.0.2 [10/Jul/2021:18:11:17 +0000] "POST / HTTP/1.1" 200 174 "-" "GitHub-Hookshot/7621ac9"
smee_1      | POST http://spackbot:8080/ - 200
```

If there are any errors they will appear there.
