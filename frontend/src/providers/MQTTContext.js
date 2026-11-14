import { createContext, useContext, useState, useEffect, useRef, useCallback, useMemo } from 'react';
import mqtt from 'mqtt'
import Alert from '@mui/material/Alert';
import Snackbar from '../components/Snackbar';

const MQTTContext = createContext();

export const useMQTT = () => useContext(MQTTContext);

const hasOwn = Object.prototype.hasOwnProperty;

const normalizeTopics = (topics) => {
  const list = Array.isArray(topics) ? topics : [topics];
  const unique = [];
  const seen = new Set();

  for (const topic of list) {
    if (!topic || seen.has(topic)) continue;
    seen.add(topic);
    unique.push(topic);
  }

  return unique;
};

class TrieNode {
  constructor() {
    this.children = {};
    this.handlers = {};
  }
}

const getOrCreateTopicNode = (root, topic) => {
  let node = root;
  const levels = topic.split('/');

  for (const level of levels) {
    if (!node.children[level]) {
      node.children[level] = new TrieNode();
    }
    node = node.children[level];
  }

  return node;
};

const addHandlerToTrie = (root, topic, handler, key) => {
  const node = getOrCreateTopicNode(root, topic);
  const hadHandler = hasOwn.call(node.handlers, key);
  node.handlers[key] = handler;
  return !hadHandler;
};

const removeHandlersFromTrie = (root, topic, key) => {
  const levels = topic.split('/');
  const path = [];
  let node = root;

  for (const level of levels) {
    const nextNode = node.children[level];
    if (!nextNode) {
      return false;
    }
    path.push([node, level, nextNode]);
    node = nextNode;
  }

  if (!node || !hasOwn.call(node.handlers, key)) {
    return false;
  }

  delete node.handlers[key];

  for (let i = path.length - 1; i >= 0; i -= 1) {
    const [parent, level, child] = path[i];
    if (Object.keys(child.handlers).length || Object.keys(child.children).length) {
      break;
    }
    delete parent.children[level];
  }

  return true;
};

const forEachHandlerInTrie = (root, topic, visitHandler) => {
  const levels = topic.split('/');
  const emitHandlers = (node) => {
    for (const handlerKey in node.handlers) {
      if (hasOwn.call(node.handlers, handlerKey)) {
        visitHandler(node.handlers[handlerKey]);
      }
    }
  };

  const search = (index, currentNode) => {
    if (!currentNode) {
      return;
    }

    if (index === levels.length) {
      emitHandlers(currentNode);
      return;
    }

    const level = levels[index];

    // Check for exact match or wildcard '+'
    if (currentNode.children[level]) {
      search(index + 1, currentNode.children[level]);
    }
    if (currentNode.children['+']) {
      search(index + 1, currentNode.children['+']);
    }

    // Check for multi-level wildcard '#'
    if (currentNode.children['#']) {
      emitHandlers(currentNode.children['#']);
    }
  };

  search(0, root);
};


export const getMqttEndpoint = ({ ui_use_proxy = 'true', ws_protocol = 'ws', broker_address = '', broker_ws_port = 9001 }, location = window.location) => {
  const useProxy = !['false', '0', 'no', 'off'].includes(String(ui_use_proxy).toLowerCase());
  const protocol = useProxy ? (location.protocol === 'https:' ? 'wss' : 'ws') : ws_protocol;
  const hosts = useProxy
    ? [location.hostname]
    : broker_address.split(';').map(host => host.trim()).filter(Boolean);
  const port = useProxy
    ? Number(location.port || (protocol === 'wss' ? 443 : 80))
    : Number(broker_ws_port);
  return { servers: hosts.map(host => ({ host, port, protocol })), protocol };
};

export const MQTTProvider = ({ name, config, children }) => {
  const [client, setClient] = useState(null);
  const topicTrie = useRef(new TrieNode());
  const topicRefCounts = useRef(new Map());
  const [error, setError] = useState(null);

  const mqttConfig = config?.mqtt ?? {};
  const {
    username,
    password,
    ui_use_proxy = 'true',
    ws_protocol = 'ws',
    broker_address = 'localhost',   // may be "addr1;addr2;addr3"
    broker_ws_port = 9001,
  } = mqttConfig;
  const hasConfig = Boolean(config && Object.keys(config).length);

  useEffect(() => {
    setClient(null);
    setError(null);
    if (!hasConfig) return;

    const { servers, protocol } = getMqttEndpoint({ ui_use_proxy, ws_protocol, broker_address, broker_ws_port });
    if (!servers.length) {
      setError('No MQTT broker configured. Check mqtt.broker_address.');
      return;
    }

    let isActive = true;
    let authenticationFailed = false;
    // MQTT.js owns timeouts, broker rotation, and retries, including initial failures.
    const mqttClient = mqtt.connect({
      servers,
      protocol,
      path: '/mqtt',
      username,
      password,
      // Send client traffic before lighttpd's default 60-second idle-read timeout.
      keepalive: 30,
      clean: true,
      connectTimeout: 10000,
      reconnectPeriod: 5000,
      reconnectOnConnackError: true,
    });

    mqttClient.on('connect', () => {
      if (!isActive) return;
      console.log(`Connected to MQTT broker for ${name}.`);
      setError(null);
      setClient(mqttClient);
    });
    mqttClient.on('message', (topic, message, packet) => {
      if (!isActive) return;
      forEachHandlerInTrie(topicTrie.current, topic, (handler) => {
        handler(topic, message, packet);
      });
    });
    mqttClient.on('error', err => {
      if (!isActive || err?.message === 'client disconnecting') return;
      // MQTT 3 and MQTT 5 codes for bad credentials / unauthorized access.
      if ([4, 5, 134, 135].includes(err.code)) {
        authenticationFailed = true;
        setError('MQTT authentication failed. Check mqtt.username and mqtt.password.');
        mqttClient.end(true);
      } else {
        setError('MQTT disconnected. Reconnecting automatically...');
      }
    });
    mqttClient.on('close', () => {
      if (!isActive || authenticationFailed) return;
      setError('MQTT disconnected. Reconnecting automatically...');
    });

    return () => {
      isActive = false;
      // Also cancels an initial connection and MQTT.js reconnect timers.
      mqttClient.end(true);
    };
  }, [
    broker_address,
    broker_ws_port,
    hasConfig,
    name,
    password,
    username,
    ws_protocol,
    ui_use_proxy,
  ]);

  useEffect(() => () => {
    topicTrie.current = new TrieNode();
    topicRefCounts.current.clear();
  }, []);

  useEffect(() => {
    if (!client) return;
    const topics = Array.from(topicRefCounts.current.keys());
    if (topics.length) {
      client.subscribe(topics, { qos: 0 });
    }
  }, [client]);

  // 1. Memoize subscribe/unsubscribe so they don't get recreated every render
  const subscribeToTopic = useCallback((topic_or_topics, messageHandler, key) => {
    const topics = normalizeTopics(topic_or_topics);
    if (!topics.length) return;
    const topicsToSubscribe = [];

    topics.forEach(topic => {
      const isNewHandler = addHandlerToTrie(topicTrie.current, topic, messageHandler, key);
      if (!isNewHandler) return;

      const currentCount = topicRefCounts.current.get(topic) ?? 0;
      const nextCount = currentCount + 1;
      topicRefCounts.current.set(topic, nextCount);
      if (client && nextCount === 1) {
        topicsToSubscribe.push(topic);
      }
    });

    if (client && topicsToSubscribe.length) {
      client.subscribe(topicsToSubscribe, { qos: 0 });
    }
  }, [client]);

  const unsubscribeFromTopic = useCallback((topic_or_topics, key) => {
    const topics = normalizeTopics(topic_or_topics);
    if (!topics.length) return;
    const topicsToUnsubscribe = [];

    topics.forEach(topic => {
      const removed = removeHandlersFromTrie(topicTrie.current, topic, key);
      if (!removed) return;

      const currentCount = topicRefCounts.current.get(topic) ?? 0;
      if (currentCount <= 1) {
        topicRefCounts.current.delete(topic);
        topicsToUnsubscribe.push(topic);
      } else {
        topicRefCounts.current.set(topic, currentCount - 1);
      }
    });

    if (client && topicsToUnsubscribe.length) {
      client.unsubscribe(topicsToUnsubscribe);
    }
  }, [client]);

  const handleCloseSnackbar = useCallback(() => {
    setError(null);
  }, []);

  const contextValue = useMemo(() => ({
    client,
    subscribeToTopic,
    unsubscribeFromTopic
  }), [client, subscribeToTopic, unsubscribeFromTopic]);

  return (
    <MQTTContext.Provider value={contextValue}>
      {children}
      <Snackbar sx={{ maxWidth: "500px" }} open={!!error} message={error ?? ""} autoHideDuration={null} onClose={handleCloseSnackbar}>
        <Alert onClose={handleCloseSnackbar} severity="error" variant="filled">
          {error}
        </Alert>
      </Snackbar>
    </MQTTContext.Provider>
  );
};
