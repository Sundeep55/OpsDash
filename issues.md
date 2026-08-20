Here are the issues i see

1. whne merging a branch to main i see below error
```
  FAIL  payload that is a JSON array
        rejected, but not for 'JSON object': ERROR: Could not read any fields from /tmp/builds/dcs/dcs-cust-inst-poc/request-schema.yaml.
===========================================================================
  0 passed, 39 failed
===========================================================================
```
2. i commented out the test-cases.sh part in pipeline merged it and then proceeded to check but when i used the gitlab pages and deployed i see this again here in the new pipeline

```
...
...
...
...
$ chmod +x ./pipeline-scripts/*.sh
$ ./pipeline-scripts/scaffold-namespace.sh
===========================================================================
                           Loading Request Payload                         
===========================================================================
===========================================================================
ERROR: Could not read any fields from ./request-schema.yaml.
===========================================================================
```
