import { createContext, useContext, useState, useEffect, useRef } from 'react';
import mqtt from 'mqtt';
import MQTTPattern from 'mqtt-pattern'

const MQTTContext = createContext();

export const useMQTT = () => useContext(MQTTContext);


export const MQTTProvider = ({ config, children }) => {
  const [client, setClient] = useState(null);
  const [topicHandlers, setTopicHandlers] = useState({});
  const topicHandlersRef = useRef(topicHandlers);

  useEffect(() => {
    topicHandlersRef.current = topicHandlers;
  }, [topicHandlers]);


  useEffect(() => {
    if (Object.keys(config).length) {
      const { username, password, ws_protocol, broker_address, broker_ws_port } = config.mqtt;
      const mqttClient = mqtt.connect(`${ws_protocol}://${broker_address}:${broker_ws_port || 9001}/mqtt`, {
        username: username || 'pioreactor',
        password: password || 'raspberry',
      });

      mqttClient.on('connect', () => {
        console.log('Connected to MQTT broker');
      });

      mqttClient.on('message', (topic, message, packet) => {

        // Iterate over the topicHandlers to find a matching pattern
        Object.keys(topicHandlersRef.current).forEach((pattern) => {
          if (MQTTPattern.matches(pattern, topic)) {
            var handler = topicHandlersRef.current[pattern];
            handler(topic, message, packet);
          }
        });
      });

      setClient(mqttClient);

      return () => {
        mqttClient.end();
      };
    }
  }, [config]);


  const subscribeToTopic = (topic, messageHandler) => {
    client?.subscribe(topic, (err) => {
      if (!err) {
        setTopicHandlers((prevHandlers) => {
          const newHandlers = { ...prevHandlers, [topic]: messageHandler };
          return newHandlers;
        });
      } else {
        console.error(`Error subscribing to topic ${topic}:`, err);
      }
    });
  };

  return (
    <MQTTContext.Provider value={{ client, subscribeToTopic }}>
      {children}
    </MQTTContext.Provider>
  );
};


