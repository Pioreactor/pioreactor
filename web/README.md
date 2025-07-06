# PioreactorUI backend


### Starting development

```
TESTING=1 python3 -m flask --debug --app pioreactorui/main run -p 4999
```

Run background workers with:

```
TESTING=1 huey_consumer pioreactorui.tasks.huey -n -b 1.0 -w 6 -f -C -d 0.05
```

### Production

This is behind a lighttpd web server on the RPi.


### Contributions

#### Adding an automation

You can add a X automation option by adding to a `.yaml` file to `backend/contrib/automations/X` folder. There is an example file under `backend/contrib/automations/automation.yaml.example`. The new automation will appear in the dialog to switch automations on the /pioreactors page.


#### Adding a job

See the examples in `backend/contrib/background_jobs`. Under the hood, this runs `pio run <job_name>`.
