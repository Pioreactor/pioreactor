import React from 'react'
import Card from '@material-ui/core/Card';
import CardContent from '@material-ui/core/CardContent';
import Button from '@material-ui/core/Button';



const AllUnitsCard = () => {
    return (
      <Card variant="outlined">
        <CardContent>
          <Button variant="outlined" color="secondary">
          Stop all processes
          </Button>
        </CardContent>
      </Card>
    )
}

export default AllUnitsCard;
