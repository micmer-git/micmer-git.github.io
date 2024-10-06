async function fetchStravaData() {
  console.log('Fetching Strava data from /api/strava-data');
  try {
    const response = await fetch('/api/strava-data');
    if (!response.ok) {
      if (response.status === 401) {
        console.warn('Unauthorized access, redirecting to landing page');
        window.location.href = '/'; // Redirect to landing page if unauthorized
      }
      throw new Error(`Network response was not ok: ${response.statusText}`);
    }
    const data = await response.json();
    console.log('Strava data fetched successfully:', data);
    displayDashboard(data);
    document.getElementById('loading').style.display = 'none'; // Hide loading indicator
    // Show dashboard sections
    document.querySelectorAll('.rank-section, .lifetime-stats, .weekly-stats').forEach(section => {
      section.style.display = 'block';
    });
  } catch (error) {
    console.error('Error fetching Strava data:', error);
    document.getElementById('dashboard-container').innerHTML = '<p>Error loading data.</p>';
  }
}

function displayDashboard(data) {
  console.log('Displaying dashboard with data:', data);

  const stravaData = {
    athlete: data.athlete,
    activities: data.activities,
    totals: data.totals,
  };

  // Your existing displayData function to render the dashboard
  displayData(stravaData);
}

function displayData(stravaData) {
  console.log('Rendering dashboard with Strava data');

  // Calculate Rank
  const totalPoints = stravaData.totals.hours; // Or any other logic
  console.log(`Total Points: ${totalPoints}`);

  const rankInfo = calculateRank(totalPoints);
  console.log('Rank Info:', rankInfo);

  // Update Rank Section
  const currentRankElement = document.getElementById('current-rank');
  const rankEmojiElement = document.getElementById('rank-emoji');
  const progressBarElement = document.getElementById('progress-bar');
  const currentRankLabelElement = document.getElementById('current-rank-label');
  const nextRankLabelElement = document.getElementById('next-rank-label');
  const currentPointsElement = document.getElementById('current-points');
  const nextRankPointsElement = document.getElementById('next-rank-points');

  if (!currentRankElement || !rankEmojiElement || !progressBarElement || !currentRankLabelElement || !nextRankLabelElement || !currentPointsElement || !nextRankPointsElement) {
    console.error('One or more rank-related DOM elements are missing.');
    return;
  }

  currentRankElement.textContent = rankInfo.currentRank.name;
  rankEmojiElement.textContent = rankInfo.currentRank.emoji;
  progressBarElement.style.width = `${rankInfo.progressPercent}%`;
  currentRankLabelElement.textContent = rankInfo.currentRank.name;
  nextRankLabelElement.textContent = rankInfo.nextRank.name;
  currentPointsElement.textContent = totalPoints;
  nextRankPointsElement.textContent = rankInfo.nextRank.minPoints;

  // Populate Rank Tooltip
  const rankListElement = document.getElementById('rank-list');
  if (!rankListElement) {
    console.error('Rank list element is missing.');
  } else {
    rankListElement.innerHTML = '';
    rankConfig.forEach(rank => {
      const li = document.createElement('li');
      li.textContent = `${rank.name} (${rank.minPoints} pts)`;
      rankListElement.appendChild(li);
    });
    console.log('Rank tooltip populated');
  }

  // Weekly Totals
  const currentWeekActivities = stravaData.activities.filter(activity => {
    const activityDate = new Date(activity.start_date);
    const today = new Date();
    const oneWeekAgo = new Date();
    oneWeekAgo.setDate(today.getDate() - 7);
    return activityDate >= oneWeekAgo && activityDate <= today;
  });

  console.log(`Found ${currentWeekActivities.length} activities in the past week`);

  const weeklyTotals = {
    hours: currentWeekActivities.reduce((sum, activity) => sum + (activity.duration / 3600), 0),
    distance: currentWeekActivities.reduce((sum, activity) => sum + activity.distance, 0),
    elevation: currentWeekActivities.reduce((sum, activity) => sum + activity.total_elevation_gain, 0),
    calories: currentWeekActivities.reduce((sum, activity) => sum + (activity.kilojoules || 0), 0),
  };

  console.log('Weekly Totals:', weeklyTotals);

  // Get Lifetime Stats
  const lifetimeStats = getLifetimeStats(stravaData.totals, weeklyTotals);
  console.log('Lifetime Stats:', lifetimeStats);

  // Update Lifetime Stats Section
  const distanceValueElement = document.getElementById('distance-value');
  const distanceWeekGainElement = document.getElementById('distance-week-gain');
  const elevationValueElement = document.getElementById('elevation-value');
  const elevationWeekGainElement = document.getElementById('elevation-week-gain');
  const caloriesValueElement = document.getElementById('calories-value');
  const caloriesWeekGainElement = document.getElementById('calories-week-gain');

  if (!distanceValueElement || !distanceWeekGainElement || !elevationValueElement || !elevationWeekGainElement || !caloriesValueElement || !caloriesWeekGainElement) {
    console.error('One or more lifetime stats DOM elements are missing.');
  } else {
    distanceValueElement.textContent = `${lifetimeStats.distance.icons} 🚴‍♂️`;
    distanceWeekGainElement.textContent = `+${lifetimeStats.distance.weekGain} this week`;

    elevationValueElement.textContent = `${lifetimeStats.elevation.icons} 🏔️`;
    elevationWeekGainElement.textContent = `+${lifetimeStats.elevation.weekGain} this week`;

    caloriesValueElement.textContent = `${lifetimeStats.calories.icons} 🍕`;
    caloriesWeekGainElement.textContent = `+${lifetimeStats.calories.weekGain} this week`;
  }

  // Update Weekly Stats
  const weeklyHoursElement = document.getElementById('weekly-hours');
  const weeklyDistanceElement = document.getElementById('weekly-distance');
  const weeklyElevationElement = document.getElementById('weekly-elevation');
  const weeklyCaloriesElement = document.getElementById('weekly-calories');

  if (!weeklyHoursElement || !weeklyDistanceElement || !weeklyElevationElement || !weeklyCaloriesElement) {
    console.error('One or more weekly stats DOM elements are missing.');
  } else {
    weeklyHoursElement.textContent = `${weeklyTotals.hours.toFixed(1)} hrs`;
    weeklyDistanceElement.textContent = `${(weeklyTotals.distance / 1000).toFixed(1)} km`;
    weeklyElevationElement.textContent = `${weeklyTotals.elevation} m`;
    weeklyCaloriesElement.textContent = `${weeklyTotals.calories} kcal`;
  }

  console.log('Dashboard rendering complete');
}

function calculateRank(totalPoints) {
  console.log(`Calculating rank for total points: ${totalPoints}`);
  let currentRank = rankConfig[0];
  let nextRank = rankConfig[1];

  for (let i = 0; i < rankConfig.length; i++) {
    if (totalPoints >= rankConfig[i].minPoints) {
      currentRank = rankConfig[i];
      nextRank = rankConfig[i + 1] || rankConfig[i]; // If at top rank
    } else {
      break;
    }
  }

  // Calculate progress percentage
  const pointsIntoCurrentRank = totalPoints - currentRank.minPoints;
  const pointsBetweenRanks = nextRank.minPoints - currentRank.minPoints;
  const progressPercent = (pointsIntoCurrentRank / pointsBetweenRanks) * 100;

  console.log('Calculated Rank Info:', {
    currentRank,
    nextRank,
    progressPercent,
    pointsIntoCurrentRank,
    pointsBetweenRanks,
  });

  return {
    currentRank,
    nextRank,
    progressPercent,
    pointsIntoCurrentRank,
    pointsBetweenRanks,
  };
}

function getLifetimeStats(totals, weeklyTotals) {
  console.log('Calculating lifetime stats');
  const stats = {};

  // Distance
  const totalDistanceIcons = Math.floor(totals.distance / 100000); // 100km per icon
  const weeklyDistanceIcons = Math.floor(weeklyTotals.distance / 100000);
  stats.distance = { icons: totalDistanceIcons, weekGain: weeklyDistanceIcons };

  // Elevation
  const totalElevationGems = Math.floor(totals.elevation / 1000); // 1000m per gem
  const weeklyElevationGems = Math.floor(weeklyTotals.elevation / 1000);
  stats.elevation = { icons: totalElevationGems, weekGain: weeklyElevationGems };

  // Calories (Pizzas)
  const totalPizzas = Math.floor(totals.calories / 1000); // 1000kcal per pizza
  const weeklyPizzas = Math.floor(weeklyTotals.calories / 1000);
  stats.calories = { icons: totalPizzas, weekGain: weeklyPizzas };

  console.log('Lifetime Stats Calculated:', stats);
  return stats;
}

// Rank System Configuration
const rankConfig = [
  { name: 'Bronze 3', emoji: '🥉', minPoints: 0 },
  { name: 'Bronze 2', emoji: '🥉', minPoints: 50 },
  { name: 'Bronze 1', emoji: '🥉', minPoints: 100 },
  { name: 'Silver 3', emoji: '🥈', minPoints: 150 },
  { name: 'Silver 2', emoji: '🥈', minPoints: 200 },
  { name: 'Silver 1', emoji: '🥈', minPoints: 250 },
  { name: 'Gold 3', emoji: '🥇', minPoints: 300 },
  { name: 'Gold 2', emoji: '🥇', minPoints: 350 },
  { name: 'Gold 1', emoji: '🥇', minPoints: 400 },
  { name: 'Platinum 3', emoji: '🏆', minPoints: 450 },
  { name: 'Platinum 2', emoji: '🏆', minPoints: 500 },
  { name: 'Platinum 1', emoji: '🏆', minPoints: 550 },
  { name: 'Diamond 3', emoji: '💎', minPoints: 600 },
  { name: 'Diamond 2', emoji: '💎', minPoints: 650 },
  { name: 'Diamond 1', emoji: '💎', minPoints: 700 },
  { name: 'Master 3', emoji: '🔥', minPoints: 750 },
  { name: 'Master 2', emoji: '🔥', minPoints: 800 },
  { name: 'Master 1', emoji: '🔥', minPoints: 850 },
  { name: 'Grandmaster 3', emoji: '🚀', minPoints: 900 },
  { name: 'Grandmaster 2', emoji: '🚀', minPoints: 950 },
  { name: 'Grandmaster 1', emoji: '🚀', minPoints: 1000 },
  { name: 'Challenger', emoji: '🌟', minPoints: 1050 },
];

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  fetchStravaData();
});
