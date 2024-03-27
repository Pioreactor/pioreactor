import { createContext, useContext, useState, useEffect, useRef } from 'react';
import mqtt from 'mqtt';
import Alert from '@mui/material/Alert';
import Snackbar from '@mui/material/Snackbar';

const MQTTContext = createContext();

export const useMQTT = () => useContext(MQTTContext);

const TrieNode = function() {
  this.children = {};
  this.handlers = []; // array to store multiple handlers
};

const addHandlerToTrie = (root, topic, handler) => {
  let node = root;
  const levels = topic.split('/');

  for (const level of levels) {
    if (!node.children[level]) {
      node.children[level] = new TrieNode();
    }
    node = node.children[level];
  }

  node.handlers.push(handler); // Add the handler to the array
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
      handlers.push(...currentNode.handlers); // Add all handlers at this node
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
      handlers.push(...currentNode.children['#'].handlers); // Add all handlers for the '#' wildcard
    }
  };

  search(0, node);

  return handlers;
};

export const MQTTProvider = ({name, config, children }) => {
  const [client, setClient] = useState(null);
  const topicTrie = useRef(new TrieNode());
  const [error, setError] = useState(null);

  useEffect(() => {
    if (Object.keys(config).length) {
      const { username, password, ws_protocol, broker_address, broker_ws_port } = config.mqtt ?? {};
      const mqttClient = mqtt.connect(`${ws_protocol ?? 'ws'}://${broker_address ?? 'localhost'}:${broker_ws_port ?? 9001}/mqtt`, {
        username: username ?? 'pioreactor',
        password: password ?? 'raspberry',
        keepalive: 2 * 60,
      });

      mqttClient.on('connect', () => {
        console.log(`Connected to MQTT broker for ${name}.`);
      });

      mqttClient.on('message', (topic, message, packet) => {
        const handlers = findHandlersInTrie(topicTrie.current, topic);
        handlers.forEach((handler) => handler(topic, message, packet));
      });

      mqttClient.on('error', (error) => {
        console.log(`MQTT ${name} connection Error: ${error}`);
        setError(`MQTT connection Error: ${error}`);
      });

      mqttClient.on('close', () => {
        console.warn(`MQTT ${name} client connection closed`);
      });


      setClient(mqttClient);

      return () => {
        mqttClient.end();
      };
    }
  }, [config, name]);

  const subscribeToTopic = (topic, messageHandler) => {
    addHandlerToTrie(topicTrie.current, topic, messageHandler);
    client?.subscribe(topic);
  };

  const handleCloseSnackbar = () => {
    setError(null);
  };

  return (
    <MQTTContext.Provider value={{ client, subscribeToTopic }}>
      {children}
      <Snackbar anchorOrigin={{vertical: "bottom", horizontal: "right"}} style={{maxWidth: "500px"}} open={!!error} autoHideDuration={6000} onClose={handleCloseSnackbar}>
        <Alert variant="standard" onClose={handleCloseSnackbar} severity="error" variant="filled">
          Failed to connect to MQTT. Is configuration for mqtt.broker_address correct? Currently set to {config?.mqtt?.broker_address}
        </Alert>
      </Snackbar>
    </MQTTContext.Provider>
  );
};