import React from 'react';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import TextField from '@mui/material/TextField';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import CircularProgress from '@mui/material/CircularProgress';
// copy-to-clipboard removed per app constraints

import {checkTaskCallback} from '../utilities';
import useCapabilityExamplesOverride from '../hooks/useCapabilityExamplesOverride';

function dedupeCapabilitiesAcrossUnits(resultByUnit) {
  // Flatten and dedupe by job_name + automation_name
  const map = new Map();
  Object.entries(resultByUnit || {}).forEach(([unit, caps]) => {
    (caps || []).forEach((cap) => {
      const key = `${cap.job_name}::${cap.automation_name || ''}`;
      const entry = map.get(key) || {
        ...cap,
        units: new Set(),
      };
      entry.units.add(unit);
      map.set(key, entry);
    });
  });
  // Convert units back to count and stable array for rendering
  return Array.from(map.values()).map((e) => ({
    ...e,
    unit_count: e.units.size,
    units: Array.from(e.units).sort(),
  }));
}

function yamlSnippetForStart(cap) {
  const job = cap.job_name;
  const automation = cap.automation_name;
  const reqArgs = (cap.arguments || []).filter((a) => a.required);
  const reqOpts = (cap.options || []).filter((o) => o.required);
  const nonReqOpts = (cap.options || [])
    .filter((o) => !o.required && o.name !== 'automation_name')
    .slice(0, 4);

  const optLines = [];
  if (automation) {
    optLines.push(`          automation_name: ${automation}`);
  }
  reqOpts.forEach((o) => {
    optLines.push(`          ${o.long_flag.replaceAll("-", "_")}: <value>`);
  });
  nonReqOpts.forEach((o) => {
    optLines.push(`          ${o.long_flag.replaceAll("-", "_")}: <value>`);
  });

  const argComment = reqArgs.length
    ? `  # required args: ${reqArgs.map((a) => a.long_flag).join(', ')} (set via 'args')\n`
    : '';

  const maybeOptions = optLines.length ? ['        options:', ...optLines] : [];

  return [
    `jobs:`,
    `  ${job}:`,
    `    actions:`,
    `      - hours_elapsed: 0`,
    `        type: start`,
    ...maybeOptions,
    argComment ? argComment.trimEnd() : undefined,
  ]
    .filter(Boolean)
    .join('\n');
}

function yamlSnippetForStartWithOverrides(cap, overrideOptions) {
  const job = cap.job_name;
  const automation = cap.automation_name;
  const optLines = [];
  const hasOverrideAutomation = Object.prototype.hasOwnProperty.call(overrideOptions || {}, 'automation_name');
  if (automation && !hasOverrideAutomation) {
    optLines.push(`          automation_name: ${automation}`);
  }
  const renderVal = (v) => (typeof v === 'string' ? JSON.stringify(v) : String(v));
  Object.entries(overrideOptions || {}).forEach(([k, v]) => {
    optLines.push(`          ${k}: ${renderVal(v)}`);
  });

  const maybeOptions = optLines.length ? ['        options:', ...optLines] : [];
  return [
    `jobs:`,
    `  ${job}:`,
    `    actions:`,
    `      - hours_elapsed: 0`,
    `        type: start`,
    ...maybeOptions,
  ].join('\n');
}

function yamlSnippetForUpdate(cap) {
  const job = cap.job_name;
  const published = cap.published_settings || {};
  const settableKeys = Object.keys(published).filter((k) => published[k] && published[k].settable && k !== '$state');
  const chosen = settableKeys.slice(0, 4);

  const optLines = chosen.length
    ? chosen.map((k) => `          ${k}: <value>`)
    : [`          <setting>: <value>`];

  return [
    `jobs:`,
    `  ${job}:`,
    `    actions:`,
    `      - hours_elapsed: 0.5`,
    `        type: update`,
    `        options:`,
    ...optLines,
  ].join('\n');
}

function yamlSnippetForUpdateWithOverrides(cap, overrideOptions) {
  const job = cap.job_name;
  const renderVal = (v) => (typeof v === 'string' ? JSON.stringify(v) : String(v));
  const optLines = Object.entries(overrideOptions || {}).map(([k, v]) => `          ${k}: ${renderVal(v)}`);
  const maybeOptions = optLines.length ? ['        options:', ...optLines] : ['        options:'];
  return [
    `jobs:`,
    `  ${job}:`,
    `    actions:`,
    `      - hours_elapsed: 0.5`,
    `        type: update`,
    ...maybeOptions,
  ].join('\n');
}

function CapabilityCard({cap}) {
  const overrides = useCapabilityExamplesOverride();
  const exactKey = `${cap.job_name}::${cap.automation_name || ''}`;
  const overrideEntry = overrides[exactKey] ?? overrides[cap.job_name];
  const hasStartUpdateShape = overrideEntry && (Object.prototype.hasOwnProperty.call(overrideEntry, 'start') || Object.prototype.hasOwnProperty.call(overrideEntry, 'update'));
  const startOpts = hasStartUpdateShape ? overrideEntry.start : overrideEntry;
  const updateOpts = hasStartUpdateShape ? overrideEntry.update : null;

  const startSnippet = startOpts
    ? yamlSnippetForStartWithOverrides(cap, startOpts)
    : yamlSnippetForStart(cap);
  const updateSnippet = updateOpts
    ? yamlSnippetForUpdateWithOverrides(cap, updateOpts)
    : yamlSnippetForUpdate(cap);
  const title = cap.automation_name
    ? `${cap.job_name} — ${cap.automation_name}`
    : cap.job_name;
  const options = cap.options || [];
  const arguments_ = cap.arguments || [];

  return (
    <Box sx={{borderBottom: '1px solid #eee', py: 1.2}}>
      <Typography variant="subtitle2" sx={{fontWeight: 600}}>{title}</Typography>
      {cap.help && (
        <Typography variant="body2" color="text.secondary" sx={{mb: 1}}>
          {cap.help}
        </Typography>
      )}
      <Stack direction="row" spacing={1} flexWrap="wrap" sx={{mb: 2}}>
        {arguments_.map((a) => (
          <Chip key={`arg-${a.name}`}  size="small" label={`arg: ${a.name.replaceAll("-", "_")}${a.required ? ' *' : ''}`} />
        ))}
        {options.map((o) => (
          <Chip key={`opt-${o.name}`} size="small" label={`${o.long_flag.replaceAll("-", "_")}${o.required ? ' *' : ''}`} />
        ))}
      </Stack>
      <Stack spacing={2} sx={{mt: 1}}>
        <TextField
          label="Start example"
          variant="outlined"
          size="small"
          fullWidth
          multiline
          minRows={3}
          value={startSnippet}
          InputProps={{readOnly: true}}
          sx={{
            '& .MuiInputBase-input': {fontFamily: 'monospace', fontSize: '0.8rem'},
          }}
        />
        {Object.keys(cap.published_settings || {}).filter((k) => cap.published_settings[k] && cap.published_settings[k].settable && k !== '$state').length !== 0 && (
        <TextField
          label="Update example"
          variant="outlined"
          size="small"
          fullWidth
          multiline
          minRows={3}
          value={updateSnippet}
          InputProps={{readOnly: true}}
          sx={{
            '& .MuiInputBase-input': {fontFamily: 'monospace', fontSize: '0.8rem'},
          }}
        />)}
      </Stack>
    </Box>
  );
}

export default function CapabilitiesPanel() {
  const [caps, setCaps] = React.useState([]);
  const [query, setQuery] = React.useState('');
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState('');

  React.useEffect(() => {
    let mounted = true;
    async function fetchCaps() {
      setLoading(true);
      setError('');
      try {
        const r = await fetch('/api/units/$broadcast/capabilities');
        const j = await r.json();
        if (!j.result_url_path) {
          throw new Error('No result_url_path');
        }
        const final = await checkTaskCallback(j.result_url_path, {delayMs: 400});
        const deduped = dedupeCapabilitiesAcrossUnits(final.result || {});
        if (mounted) setCaps(deduped);
      } catch (e) {
        if (mounted) setError('Failed to load capabilities');
      } finally {
        if (mounted) setLoading(false);
      }
    }
    fetchCaps();
    return () => {
      mounted = false;
    };
  }, []);

  const filtered = caps.filter((c) => {
    const t = `${c.job_name} ${c.automation_name || ''} ${(c.help || '')}`.toLowerCase();
    return t.includes(query.toLowerCase());
  });

  return (
      <>
        <Typography variant="body2" color="text.secondary" sx={{mb: 1}}>
          Browse jobs and automations available across your cluster.
        </Typography>
        <TextField
          size="small"
          placeholder="Search jobs, automations, help…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          fullWidth
          sx={{mb: 1}}
        />
        {loading && (
          <Box sx={{textAlign: 'center', py: 4}}>
            <CircularProgress size={28} />
          </Box>
        )}
        {!loading && error && (
          <Typography variant="body2" color="error">{error}</Typography>
        )}
        {!loading && !error && (
          <Box sx={{overflow: 'auto'}}>
            {filtered.map((c) => (
              <CapabilityCard key={`${c.job_name}::${c.automation_name || ''}`} cap={c} />
            ))}
            {filtered.length === 0 && (
              <Typography variant="body2" color="text.secondary" sx={{py: 2}}>
                No matches.
              </Typography>
            )}
          </Box>
        )}
      </>
  );
}
