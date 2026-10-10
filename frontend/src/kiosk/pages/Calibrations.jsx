import { useMemo, useState } from "react";
import { enc, unitApi } from "../api";
import { useAsync } from "../hooks";
import { Icon } from "../icons";
import { AsyncButton, Empty, Sheet, useConfirm, useToast } from "../ui";
import XYChart from "../XYChart";
import CalibrationSession, { readStoredSession } from "./CalibrationSession";

// Calibrations at the bench. Everything here is unit-local (/unit_api), so it
// works while the leader is unreachable.

// Jobs a protocol needs off, mirroring the checks the protocols make when a
// session starts. The unit stays the authority: it refuses to start otherwise.
const REQUIRES_OFF = {
  dc_based: ["stirring"],
  standards: ["stirring", "od_reading"],
  od_fusion_standards: ["stirring", "od_reading"],
  manual_focus: ["od_reading", "stirring", "dosing_automation", "led_automation"],
};

const humanize = (name) => name.replace(/_/g, " ");

function formatDate(timestamp) {
  const ms = Date.parse(timestamp);
  return Number.isFinite(ms) ? new Date(ms).toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" }) : "";
}

const newestFirst = (a, b) => (Date.parse(b.created_at) || 0) - (Date.parse(a.created_at) || 0);

async function waitUntilStopped(jobs, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const running = await unitApi("/jobs/running");
    if (!running.some((row) => jobs.includes(row.job_name))) return;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`${jobs.map(humanize).join(", ")} didn't stop in time. Check Logs.`);
}

function ProtocolSheet({ protocol, onClose, onStart }) {
  const confirm = useConfirm();
  const toast = useToast();
  const mustBeOff = REQUIRES_OFF[protocol.protocol_name] || [];

  const start = async () => {
    if (mustBeOff.length) {
      const running = (await unitApi("/jobs/running")).map((row) => row.job_name).filter((job) => mustBeOff.includes(job));
      const conflicting = [...new Set(running)];
      if (conflicting.length) {
        const names = conflicting.map(humanize).join(" and ");
        const ok = await confirm({
          title: `Stop ${names}?`,
          message: `This calibration needs ${names} off. Stop ${conflicting.length > 1 ? "them" : "it"} and continue?`,
          confirmText: "Stop and continue",
          danger: true,
        });
        if (!ok) return;
        await Promise.all(conflicting.map((job) => unitApi("/jobs/stop", { method: "POST", body: { job_name: job } })));
        toast(`Stopping ${names}...`);
        await waitUntilStopped(conflicting);
      }
    }
    onStart(protocol);
  };

  return (
    <Sheet
      title={protocol.title}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <AsyncButton className="btn primary" onClick={start} busyLabel="Checking...">
            <Icon name="play" />
            Start calibration
          </AsyncButton>
        </>
      }
    >
      {protocol.description && <p>{protocol.description}</p>}
      {protocol.requirements?.length > 0 && (
        <>
          <h3 className="section-title">You'll need</h3>
          <ul className="requirements">
            {protocol.requirements.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}
      {mustBeOff.length > 0 && <p className="muted">Needs {mustBeOff.map(humanize).join(", ")} off while it runs.</p>}
    </Sheet>
  );
}

function CalibrationSheet({ device, calibration, onClose, onChanged }) {
  const toast = useToast();
  const series = useMemo(() => {
    const xs = calibration.recorded_data?.x || [];
    const ys = calibration.recorded_data?.y || [];
    if (!xs.length || !Array.isArray(xs) || typeof xs[0] !== "number") return null;
    return [{ id: "recorded", label: "Recorded", points: xs.map((x, i) => ({ x, y: ys[i] })), curve: calibration.curve_data_ }];
  }, [calibration]);

  const setActive = async () => {
    await unitApi(`/active_calibrations/${enc(device)}/${enc(calibration.calibration_name)}`, { method: "PATCH" });
    toast(`${calibration.calibration_name} is now active for ${humanize(device)}`);
    onChanged();
    onClose();
  };

  const clearActive = async () => {
    await unitApi(`/active_calibrations/${enc(device)}`, { method: "DELETE" });
    toast(`${humanize(device)} has no active calibration`);
    onChanged();
    onClose();
  };

  return (
    <Sheet
      title={calibration.calibration_name}
      onClose={onClose}
      footer={
        calibration.is_active ? (
          <AsyncButton className="btn" onClick={clearActive}>
            Set inactive
          </AsyncButton>
        ) : (
          <AsyncButton className="btn primary" onClick={setActive}>
            <Icon name="check" />
            Set active
          </AsyncButton>
        )
      }
    >
      <p className="muted">
        {humanize(device)} · {formatDate(calibration.created_at)}
        {calibration.is_active ? " · active" : ""}
      </p>
      {series ? (
        <div className="sheet-chart">
          <XYChart series={series} xLabel={calibration.x} yLabel={calibration.y} />
        </div>
      ) : (
        <p className="muted">This calibration has no data to plot.</p>
      )}
    </Sheet>
  );
}

function SavedRow({ name, createdAt, active, onClick }) {
  return (
    <button type="button" className="list-row" onClick={onClick}>
      <div className="grow">
        <div className="truncate strong">{name}</div>
        <div className="sub">{formatDate(createdAt)}</div>
      </div>
      {active && <span className="badge ready">Active</span>}
      <Icon name="forward" />
    </button>
  );
}

function DevicePanel({ device, protocols, calibrations, estimators, activeEstimator, onStart, onChanged }) {
  const toast = useToast();
  const [protocol, setProtocol] = useState(null);
  const [calibration, setCalibration] = useState(null);

  const activateEstimator = async (estimator) => {
    if (estimator.estimator_name === activeEstimator) {
      await unitApi(`/active_estimators/${enc(device)}`, { method: "DELETE" });
      toast(`${humanize(device)} has no active estimator`);
    } else {
      await unitApi(`/active_estimators/${enc(device)}/${enc(estimator.estimator_name)}`, { method: "PATCH" });
      toast(`${estimator.estimator_name} is now active for ${humanize(device)}`);
    }
    onChanged();
  };

  return (
    <div className="device-panel">
      {protocols.length > 0 && (
        <>
          <h2 className="section-title">New calibration</h2>
          <div className="protocols">
            {protocols.map((candidate) => (
              <button type="button" key={candidate.id} className="protocol" onClick={() => setProtocol(candidate)}>
                <strong>{candidate.title}</strong>
                {candidate.description && <span className="sub">{candidate.description}</span>}
              </button>
            ))}
          </div>
        </>
      )}

      {calibrations.length > 0 && (
        <>
          <h2 className="section-title">Calibrations</h2>
          <div className="list">
            {calibrations.map((cal) => (
              <SavedRow
                key={cal.calibration_name}
                name={cal.calibration_name}
                createdAt={cal.created_at}
                active={cal.is_active}
                onClick={() => setCalibration(cal)}
              />
            ))}
          </div>
        </>
      )}

      {estimators.length > 0 && (
        <>
          <h2 className="section-title">Estimators</h2>
          <div className="list">
            {estimators.map((estimator) => {
              const active = estimator.estimator_name === activeEstimator;
              return (
                <div className="list-row" key={estimator.estimator_name}>
                  <div className="grow">
                    <div className="truncate strong">{estimator.estimator_name}</div>
                    <div className="sub">{formatDate(estimator.created_at)}</div>
                  </div>
                  {active && <span className="badge ready">Active</span>}
                  <AsyncButton className="btn" onClick={() => activateEstimator(estimator)}>
                    {active ? "Set inactive" : "Set active"}
                  </AsyncButton>
                </div>
              );
            })}
          </div>
        </>
      )}

      {!protocols.length && !calibrations.length && !estimators.length && <Empty>Nothing to calibrate for this device.</Empty>}

      {protocol && (
        <ProtocolSheet
          protocol={protocol}
          onClose={() => setProtocol(null)}
          onStart={(chosen) => {
            setProtocol(null);
            onStart(chosen);
          }}
        />
      )}
      {calibration && (
        <CalibrationSheet device={device} calibration={calibration} onClose={() => setCalibration(null)} onChanged={onChanged} />
      )}
    </div>
  );
}

export default function Calibrations() {
  const toast = useToast();
  const data = useAsync(
    (signal) =>
      Promise.all([
        unitApi("/calibration_protocols", { signal }),
        unitApi("/calibrations", { signal }).catch(() => ({})),
        unitApi("/estimators", { signal }).catch(() => ({})),
        unitApi("/active_estimators", { signal }).catch(() => ({})),
      ]),
    [],
  );
  const [selected, setSelected] = useState(null);
  const [session, setSession] = useState(() => {
    const stored = readStoredSession();
    return stored ? { sessionId: stored } : null;
  });

  const [protocols, calibrations, estimators, activeEstimators] = data.data || [[], {}, {}, {}];

  const devices = useMemo(() => {
    const names = new Set([
      ...protocols.map((p) => p.target_device),
      ...Object.keys(calibrations || {}),
      ...Object.keys(estimators || {}),
    ]);
    return [...names].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  }, [protocols, calibrations, estimators]);

  const device = devices.includes(selected) ? selected : devices[0];
  const activeName = (name) => (calibrations?.[name] || []).find((cal) => cal.is_active)?.calibration_name || activeEstimators?.[name]?.estimator_name;

  if (data.error && !data.data) return <Empty>Could not load calibrations: {data.error}</Empty>;
  if (!data.data) return <Empty>Loading calibrations...</Empty>;

  return (
    <div className="split">
      <nav className="device-list" aria-label="Devices">
        {devices.map((name) => {
          const active = activeName(name);
          return (
            <button
              type="button"
              key={name}
              className={`device ${name === device ? "on" : ""}`}
              aria-current={name === device ? "true" : undefined}
              onClick={() => setSelected(name)}
            >
              <span className="truncate strong">{humanize(name)}</span>
              <span className="sub truncate">{active ? `Active: ${active}` : "No active calibration"}</span>
            </button>
          );
        })}
      </nav>
      <div className="content">
        {device && (
          <DevicePanel
            key={device}
            device={device}
            protocols={protocols.filter((p) => p.target_device === device)}
            calibrations={[...(calibrations?.[device] || [])].sort(newestFirst)}
            estimators={[...(estimators?.[device] || [])].sort(newestFirst)}
            activeEstimator={activeEstimators?.[device]?.estimator_name}
            onStart={(protocol) => setSession({ protocol })}
            onChanged={data.reload}
          />
        )}
      </div>
      {session && (
        <CalibrationSession
          protocol={session.protocol}
          sessionId={session.sessionId}
          onClose={(changed) => {
            setSession(null);
            if (changed) {
              data.reload();
              toast("Calibrations updated");
            }
          }}
        />
      )}
    </div>
  );
}
