# PyServe

A single file CGI server implemented in Python.

## Tutorial

Create a new file called `hello.py` with the following content:

```python
#!/usr/bin/env python3

from pyserve import http

print(f"Hi {http.GET['name']}!")
```

_You must import pyserve even if you are not using it. Otherwise, you need to explicitly write the correct HTTP headers for your script_

Make the file executable:

```bash
chmod +x hello.py
```

Start the server:

```bash
python3 pyserve.py
```

Open `http://localhost:8000/hello.py?name=Meir` in your browser.

You should see the following output:

```
Hi! ['Meir']
```

## Performance

Due to the fact that a new process is created for each request, the performance is not very good.

```python
#!/usr/bin/env python3

import pyserve

print("Hello World!")
```

```text
ab -n 500 -c 50 http://127.0.0.1:8000/hello_world.py
This is ApacheBench, Version 2.3 <$Revision: 1901567 $>
Copyright 1996 Adam Twiss, Zeus Technology Ltd, http://www.zeustech.net/
Licensed to The Apache Software Foundation, http://www.apache.org/

Benchmarking 127.0.0.1 (be patient)
Completed 100 requests
Completed 200 requests
Completed 300 requests
Completed 400 requests
Completed 500 requests
Finished 500 requests


Server Software:        
Server Hostname:        127.0.0.1
Server Port:            8000

Document Path:          /hello_world.py
Document Length:        13 bytes

Concurrency Level:      50
Time taken for tests:   6.108 seconds
Complete requests:      500
Failed requests:        0
Total transferred:      38500 bytes
HTML transferred:       6500 bytes
Requests per second:    81.86 [#/sec] (mean)
Time per request:       610.768 [ms] (mean)
Time per request:       12.215 [ms] (mean, across all concurrent requests)
Transfer rate:          6.16 [Kbytes/sec] received

Connection Times (ms)
              min  mean[+/-sd] median   max
Connect:        0    0   0.7      0       5
Processing:    88  591 150.9    569     993
Waiting:       87  570 146.2    548     990
Total:         89  591 151.1    569     993

Percentage of the requests served within a certain time (ms)
  50%    569
  66%    648
  75%    700
  80%    724
  90%    777
  95%    848
  98%    959
  99%    962
 100%    993 (longest request)
```

Only ~80 requests per second. And let's compare it to Flask:

```python
from flask import Flask

app = Flask(__name__)

@app.route("/")
def ping():
    return "Hello World!"
```

```text
ab -n 500 -c 50 http://127.0.0.1:8000/            
This is ApacheBench, Version 2.3 <$Revision: 1901567 $>
Copyright 1996 Adam Twiss, Zeus Technology Ltd, http://www.zeustech.net/
Licensed to The Apache Software Foundation, http://www.apache.org/

Benchmarking 127.0.0.1 (be patient)
Completed 100 requests
Completed 200 requests
Completed 300 requests
Completed 400 requests
Completed 500 requests
Finished 500 requests


Server Software:        gunicorn
Server Hostname:        127.0.0.1
Server Port:            8000

Document Path:          /
Document Length:        12 bytes

Concurrency Level:      50
Time taken for tests:   0.158 seconds
Complete requests:      500
Failed requests:        0
Total transferred:      82500 bytes
HTML transferred:       6000 bytes
Requests per second:    3157.24 [#/sec] (mean)
Time per request:       15.837 [ms] (mean)
Time per request:       0.317 [ms] (mean, across all concurrent requests)
Transfer rate:          508.74 [Kbytes/sec] received

Connection Times (ms)
              min  mean[+/-sd] median   max
Connect:        0    0   0.5      0       2
Processing:     2   15   4.0     13      28
Waiting:        1   15   4.0     13      28
Total:          4   15   4.1     13      29

Percentage of the requests served within a certain time (ms)
  50%     13
  66%     14
  75%     16
  80%     18
  90%     22
  95%     25
  98%     27
  99%     28
 100%     29 (longest request)
```

**Note**: We run the server with `gunicorn app:app`.

~3150 requests per second (**x40 times faster**). This is a huge difference, and we can achieve better results if we increase the number of workers.
