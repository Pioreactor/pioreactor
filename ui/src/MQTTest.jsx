import React, { useState, Fragment } from 'react';

import {Client, Message} from 'paho-mqtt';

function MQTTest() {
  var note;

  var client = new Client("localhost", 9001, "webui");

  client.connect({onSuccess:onConnect});
  client.onMessageArrived = onMessageArrived;

  function onConnect() {
    console.log("onConnect");
    client.subscribe("test/test")
  }

  // called when a message arrives
  function onMessageArrived(message) {
    var m = message.payloadString;
    console.log("onMessageArrived:"+m);
    setMsg(m)

  }

  // Sets default React state
  const [msg, setMsg] = useState(<Fragment><em>nothing heard</em></Fragment>);

  return (
    <div>
    <p>The message is: {msg}</p>
    </div>
  );
}

export default MQTTest;
