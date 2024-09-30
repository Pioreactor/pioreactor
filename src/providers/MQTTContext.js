import { createContext, useContext, useState, useEffect, useRef } from 'react';
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

export const MQTTProvider = ({ name, config, children, experiment }) => {
  const [client, setClient] = useState(null);
  const topicTrie = useRef(new TrieNode());
  const [error, setError] = useState(null);

  useEffect(() => {
    if (Object.keys(config).length) {
      const { username, password, ws_protocol, broker_address, broker_ws_port } = config.mqtt ?? {};
      const mqttClient = mqtt.connect(`${ws_protocol ?? 'ws'}://${broker_address ?? 'localhost'}:${broker_ws_port ?? 9001}/mqtt`, {
        username,
        password,
        keepalive: 120,
        clean: true
      });

      mqttClient.on('connect', () => {
        console.log(`Connected to MQTT broker for ${name}.`);
      });

      mqttClient.on('message', (topic, message, packet) => {
        const handlers = findHandlersInTrie(topicTrie.current, topic);
        handlers.forEach(handler => handler(topic, message, packet));
      });

      mqttClient.on('error', error => {
        if (error.message === 'client disconnecting') {
          return;
        }
        console.log(`MQTT ${name} connection error: ${error}`);
        setError(`MQTT connection error: ${error}`);
      });

      mqttClient.on('close', () => {
        console.warn(`MQTT ${name} client connection closed`);
      });

      setClient(mqttClient);

      return () => {
        clearTrie(topicTrie.current);
        mqttClient.end(true);
      };
    }
  }, [config, name, experiment]);

  const subscribeToTopic = (topic_or_topics, messageHandler, key) => {
    // use the `key`` to provide unique handlers per topic (else it's overwritten)
    addHandlerToTrie(topicTrie.current, topic_or_topics, messageHandler, key);
    client.subscribe(topic_or_topics, { qos: 0 });
  };

  const unsubscribeFromTopic = (topic, key) => {
    removeHandlersFromTrie(topicTrie.current, topic, key);
    client?.unsubscribe(topic);
  };

  const handleCloseSnackbar = () => {
    setError(null);
  };

  return (
    <MQTTContext.Provider value={{ client, subscribeToTopic, unsubscribeFromTopic }}>
      {children}
      <Snackbar anchorOrigin={{ vertical: "bottom", horizontal: "right" }} style={{ maxWidth: "500px" }} open={!!error} autoHideDuration={6000} onClose={handleCloseSnackbar}>
        <Alert onClose={handleCloseSnackbar} severity="error" variant="filled">
          Failed to connect to MQTT. Is configuration for mqtt.broker_address correct? Currently set to {config?.mqtt?.broker_address}
        </Alert>
      </Snackbar>
    </MQTTContext.Provider>
  );
};