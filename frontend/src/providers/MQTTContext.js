import { createContext, useContext, useState, useEffect, useRef, useCallback, useMemo } from 'react';
import mqtt from 'mqtt'
import Alert from '@mui/material/Alert';
import Snackbar from '@mui/material/Snackbar';

const MQTTContext = createContext();

export const useMQTT = () => useContext(MQTTContext);

const clearTrie = (node) => {
  node.handlers = {}; // Clear handlers at the current node

  for (const key in node.children) {
    clearTrie(node.children[key]); // Recursively clear children
  }
};

const TrieNode = function() {
  this.children = {};
  this.handlers = {}; // Using an object to store handlers by key
};

const addHandlerToTrie = (root, topics, handler, key) => {
  // Convert a single string topic to an array
  if (!Array.isArray(topics)) {
    topics = [topics];
  }

  // Process each topic in the array
  topics.forEach(topic => {
    let node = root;
    const levels = topic.split('/');

    for (const level of levels) {
      if (!node.children[level]) {
        node.children[level] = new TrieNode();
      }
      node = node.children[level];
    }

    node.handlers[key] = handler; // Store handler with the unique key
  });
};

const removeHandlersFromTrie = (root, topic, key) => {
  let node = root;
  const levels = topic.split('/');

  for (const level of levels) {
    if (!node.children[level]) {
      return; // Topic not found
    }
    node = node.children[level];
  }

  delete node.handlers[key]; // Remove handler by key
};

const findHandlersInTrie = (root, topic) => {
  const levels = topic.split('/');
  let node = root;
  const handlers = [];

  const search = (index, currentNode) => {
    if (!currentNode) {
      return;
    }

    if (index === levels.length) {
      Object.values(currentNode.handlers).forEach(handler => handlers.push(handler));
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
      Object.values(currentNode.children['#'].handlers).forEach(handler => handlers.push(handler));
    }
  };

  search(0, node);

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
  const [error, setError] = useState(null);


  useEffect(() => {
    if (!Object.keys(config).length) return;

    const {
      username,
      password,
      ws_protocol = 'ws',
      broker_address = 'localhost',   // may be "addr1;addr2;addr3"
      broker_ws_port = 9001,
    } = config.mqtt ?? {};

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

    connectWithFallback()
      .then(c => {
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

        setClient(mqttClient);
      })
      .catch(err => {
        console.error(err);
        setError(err.message);
      });

    // ----------------- cleanup -----------------
    return () => {
      clearTrie(topicTrie.current);
      mqttClient?.end(true);
    };
  }, [config, name, experiment]);

  // 1. Memoize subscribe/unsubscribe so they don't get recreated every render
  const subscribeToTopic = useCallback((topic_or_topics, messageHandler, key) => {
    addHandlerToTrie(topicTrie.current, topic_or_topics, messageHandler, key);
    client?.subscribe(topic_or_topics, { qos: 0 });
  }, [client]);

  const unsubscribeFromTopic = useCallback((topic, key) => {
    removeHandlersFromTrie(topicTrie.current, topic, key);
    client?.unsubscribe(topic);
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
