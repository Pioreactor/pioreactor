import { createContext, useContext, useState, useEffect, useRef, useCallback, useMemo } from 'react';
import mqtt from 'mqtt'
import Alert from '@mui/material/Alert';
import Snackbar from '@mui/material/Snackbar';

const MQTTContext = createContext();

export const useMQTT = () => useContext(MQTTContext);

const normalizeTopics = (topics) => (Array.isArray(topics) ? topics : [topics]).filter(Boolean);

const resetTrie = (node) => {
  node.children = {};
  node.handlers = {};
};

const TrieNode = function() {
  this.children = {};
  this.handlers = {}; // Using an object to store handlers by key
};

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

const getTopicNode = (root, topic) => {
  let node = root;
  const levels = topic.split('/');

  for (const level of levels) {
    if (!node.children[level]) {
      return null;
    }
    node = node.children[level];
  }

  return node;
};

const addHandlerToTrie = (root, topic, handler, key) => {
  const node = getOrCreateTopicNode(root, topic);
  const hadHandler = Object.prototype.hasOwnProperty.call(node.handlers, key);
  node.handlers[key] = handler;
  return !hadHandler;
};

const removeHandlersFromTrie = (root, topic, key) => {
  const node = getTopicNode(root, topic);
  if (!node || !Object.prototype.hasOwnProperty.call(node.handlers, key)) {
    return false;
  }

  delete node.handlers[key];
  return true;
};

const findHandlersInTrie = (root, topic) => {
  const levels = topic.split('/');
  const handlers = [];

  const search = (index, currentNode) => {
    if (!currentNode) {
      return;
    }

    if (index === levels.length) {
      for (const handlerKey in currentNode.handlers) {
        handlers.push(currentNode.handlers[handlerKey]);
      }
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
      const wildcardNode = currentNode.children['#'];
      for (const handlerKey in wildcardNode.handlers) {
        handlers.push(wildcardNode.handlers[handlerKey]);
      }
    }
  };

  search(0, root);

  return handlers;
};


const CONNECT_TIMEOUT_MS = 1000;
// Retry settings for MQTT fallback connections
const RETRY_ATTEMPTS = 3;
const RETRY_DELAY_MS = 100;

// Simple sleep helper for retries
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));


export const MQTTProvider = ({ name, config, children, experiment }) => {
  const [client, setClient] = useState(null);
  const topicTrie = useRef(new TrieNode());
  const topicRefCounts = useRef(new Map());
  const [error, setError] = useState(null);

  const mqttConfig = config?.mqtt ?? {};
  const {
    username,
    password,
    ws_protocol = 'ws',
    broker_address = 'localhost',   // may be "addr1;addr2;addr3"
    broker_ws_port = 9001,
  } = mqttConfig;
  const hasConfig = Boolean(config && Object.keys(config).length);

  useEffect(() => {
    if (!hasConfig) return;
    setClient(null);
    setError(null);

    /** try a single URI, resolve on 'connect', reject on 'error' or timeout */
    const tryUri = (uri, opts) =>
      new Promise((resolve, reject) => {
        const c = mqtt.connect(uri, opts);
        const timer = setTimeout(() => {
          c.end(true);
          reject(new Error('timeout'));
        }, CONNECT_TIMEOUT_MS);

        c.once('connect', () => {
          clearTimeout(timer);
          resolve(c);       // <- SUCCESS
        });
        c.once('error', err => {
          clearTimeout(timer);
          c.end(true);
          reject(err);      // <- FAIL, will fall through to next host
        });
      });

    /** retrying sequential fallback */
    const connectWithFallback = async () => {
      const hosts = broker_address.split(';').map(h => h.trim()).filter(Boolean);
      const opts  = { username, password, keepalive: 120, clean: true };

      for (let attempt = 1; attempt <= RETRY_ATTEMPTS; attempt++) {
        for (const host of hosts) {
          const uri = `${ws_protocol}://${host}:${broker_ws_port}/mqtt`;
          try {
            console.log(`MQTT trying ${uri} (attempt ${attempt}) …`);
            return await tryUri(uri, opts); // first successful connection wins
          } catch (e) {
            console.warn(`MQTT could not connect to ${uri} (attempt ${attempt}): ${e.message}`);
          }
        }
        if (attempt < RETRY_ATTEMPTS) {
          console.log(`MQTT retrying all hosts in ${RETRY_DELAY_MS}ms...`);
          await sleep(RETRY_DELAY_MS);
        }
      }
      throw new Error('Unable to reach any MQTT broker');
    };

    let mqttClient;
    let isActive = true;

    connectWithFallback()
      .then(c => {
        if (!isActive) {
          c.end(true);
          return;
        }
        mqttClient = c;
        console.log(`Connected to MQTT broker for ${name}.`);

        mqttClient.on('message', (topic, message, packet) => {
          const handlers = findHandlersInTrie(topicTrie.current, topic);
          handlers.forEach(h => h(topic, message, packet));
        });

        mqttClient.on('error', err => {
          if (err?.message === 'client disconnecting') return;
          console.error(`MQTT ${name} connection error:`, err);
          setError(`MQTT connection error: ${err}`);
        });

        mqttClient.on('close', () => {
          console.warn(`MQTT ${name} client connection closed`);
        });

        setError(null);
        setClient(mqttClient);
      })
      .catch(err => {
        if (!isActive) return;
        console.error(err);
        setError(err.message);
      });

    // ----------------- cleanup -----------------
    return () => {
      isActive = false;
      mqttClient?.end(true);
    };
  }, [
    broker_address,
    broker_ws_port,
    hasConfig,
    name,
    password,
    username,
    ws_protocol,
  ]);

  useEffect(() => () => {
    resetTrie(topicTrie.current);
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
      <Snackbar anchorOrigin={{ vertical: "bottom", horizontal: "right" }} style={{ maxWidth: "500px" }} open={!!error} autoHideDuration={6000} onClose={handleCloseSnackbar}>
        <Alert onClose={handleCloseSnackbar} severity="error" variant="filled">
          Failed to connect to MQTT. Is configuration for mqtt.broker_address correct? Currently set to {config?.mqtt?.broker_address}
        </Alert>
      </Snackbar>
    </MQTTContext.Provider>
  );
};
