import { createContext, useContext, useState, useEffect, useRef } from 'react';
import mqtt from 'mqtt';
//import MQTTPattern from 'mqtt-pattern';

const MQTTContext = createContext();

export const useMQTT = () => useContext(MQTTContext);

const TrieNode = function() {
  this.children = {};
  this.handler = null;
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

  node.handler = handler;
};

const findHandlersInTrie = (root, topic) => {
  const levels = topic.split('/');
  const handlers = [];
  let node = root;

  const search = (index, currentNode) => {
    if (!currentNode) {
      return;
    }

    if (index === levels.length) {
      if (currentNode.handler) {
        handlers.push(currentNode.handler);
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
    if (currentNode.children['#'] && currentNode.children['#'].handler) {
      handlers.push(currentNode.children['#'].handler);
    }
  };

  search(0, node);

  return handlers;
};

export const MQTTProvider = ({name, config, children }) => {
  const [client, setClient] = useState(null);
  const topicTrie = useRef(new TrieNode());

  useEffect(() => {
    if (Object.keys(config).length) {
      const { username, password, ws_protocol, broker_address, broker_ws_port } = config.mqtt;
      const mqttClient = mqtt.connect(`${ws_protocol}://${broker_address}:${broker_ws_port || 9001}/mqtt`, {
        username: username || 'pioreactor',
        password: password || 'raspberry',
        keepalive: 2 * 60,
      });

      mqttClient.on('connect', () => {
        console.log(`Connected to ${name} MQTT broker`);
      });

      mqttClient.on('message', (topic, message, packet) => {
        const handlers = findHandlersInTrie(topicTrie.current, topic);
        handlers.forEach((handler) => handler(topic, message, packet));
      });

      setClient(mqttClient);

      return () => {
        mqttClient.end();
      };
    }
  }, [config]);

  const subscribeToTopic = (topic, messageHandler) => {
    addHandlerToTrie(topicTrie.current, topic, messageHandler);
    client?.subscribe(topic);
  };

  return (
    <MQTTContext.Provider value={{ client, subscribeToTopic }}>
      {children}
    </MQTTContext.Provider>
  );
};