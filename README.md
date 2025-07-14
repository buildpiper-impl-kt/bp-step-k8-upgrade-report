# bp-step-k8-upgrade-report


```bash
docker run -v $(pwd)/input/logs:/app/input/logs \
           -v $(pwd)/output/reports:/app/output/reports \
           eks-upgrade-reporter
```
With custom sleep duration:

```bash
docker run -e SLEEP_DURATION=10 \
           -v $(pwd)/input/logs:/app/input/logs \
           -v $(pwd)/output/reports:/app/output/reports \
           eks-upgrade-reporter
```
