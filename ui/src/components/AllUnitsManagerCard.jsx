import React from 'react'
import Card from '@material-ui/core/Card';
import CardContent from '@material-ui/core/CardContent';
import Button from '@material-ui/core/Button';



function VolumeThroughputTally() {
  const [volumeThroughput, setVolumeThroughput] = React.setState({})

  // connect, subscribe, and update volumeThroughput over time...

  return (
      <div>
      </div>
  )
}



const AllUnitsCard = () => {

    function onClick(e) {
        fetch("/stop")
    }

    return (
      <Card>
        <CardContent>
          <Button variant="outlined" color="secondary" onClick={onClick}>
          Stop all processes
          </Button>
        </CardContent>
      </Card>
    )
}

export default AllUnitsCard;
