import React from "react";

import { useMQTT } from "../providers/MQTTContext";


const CAMERA_RECOVERY_REFRESH_INTERVAL_MS = 5 * 60 * 1000;
const identity = (value) => value;


export default function useCameraResource({
  mqttTopic,
  normalize = identity,
  url,
}) {
  const { client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();
  const subscriberId = React.useId();
  const subscriberKey = `CameraResource${subscriberId}`;
  const requestVersionRef = React.useRef(0);
  const [resource, setResource] = React.useState({ url, data: undefined });
  const [loading, setLoading] = React.useState(Boolean(url));
  const [resourceError, setResourceError] = React.useState({ url, message: null });

  const data = resource.url === url ? resource.data : undefined;
  const error = resourceError.url === url ? resourceError.message : null;
  const isLoading = resource.url === url ? loading : Boolean(url);

  const setData = React.useCallback((nextData) => {
    setResource((currentResource) => {
      const currentData = currentResource.url === url ? currentResource.data : undefined;
      return {
        url,
        data: typeof nextData === "function" ? nextData(currentData) : nextData,
      };
    });
  }, [url]);

  const setError = React.useCallback((message) => {
    setResourceError({ url, message });
  }, [url]);

  const refresh = React.useCallback(async ({ signal, showLoading = true } = {}) => {
    if (!url) {
      setLoading(false);
      return;
    }

    const requestVersion = requestVersionRef.current + 1;
    requestVersionRef.current = requestVersion;
    if (showLoading) {
      setLoading(true);
    }

    try {
      const response = await fetch(url, { signal });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || "Could not refresh camera data.");
      }

      const payload = await response.json();
      if (!signal?.aborted && requestVersion === requestVersionRef.current) {
        setResource({ url, data: normalize(payload) });
        setResourceError({ url, message: null });
      }
    } catch (fetchError) {
      if (
        fetchError.name !== "AbortError"
        && requestVersion === requestVersionRef.current
      ) {
        setResourceError({ url, message: fetchError.message });
      }
    } finally {
      if (!signal?.aborted && requestVersion === requestVersionRef.current) {
        setLoading(false);
      }
    }
  }, [normalize, url]);

  React.useEffect(() => {
    if (!url) {
      setLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    void refresh({ signal: controller.signal });

    return () => {
      controller.abort();
    };
  }, [refresh, url]);

  React.useEffect(() => {
    if (!client || !mqttTopic || !url) {
      return undefined;
    }

    const controller = new AbortController();
    const onCameraStillChanged = () => {
      void refresh({ signal: controller.signal, showLoading: false });
    };
    subscribeToTopic(mqttTopic, onCameraStillChanged, subscriberKey);

    return () => {
      controller.abort();
      unsubscribeFromTopic(mqttTopic, subscriberKey);
    };
  }, [client, mqttTopic, refresh, subscribeToTopic, subscriberKey, unsubscribeFromTopic, url]);

  React.useEffect(() => {
    if (!url) {
      return undefined;
    }

    const controller = new AbortController();
    const interval = window.setInterval(() => {
      void refresh({ signal: controller.signal, showLoading: false });
    }, CAMERA_RECOVERY_REFRESH_INTERVAL_MS);

    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, [refresh, url]);

  return {
    data,
    error,
    loading: isLoading,
    refresh,
    setData,
    setError,
  };
}
